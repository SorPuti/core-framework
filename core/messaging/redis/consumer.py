"""Redis Streams consumer."""

from __future__ import annotations

from typing import Any, Callable, Awaitable
import json
import asyncio
import logging

from core.messaging.base import Consumer, Event
from core.config import get_settings
from core.messaging.registry import get_event_handlers

logger = logging.getLogger(__name__)


class RedisConsumer(Consumer):
    """Redis Streams consumer with automatic event tracking."""

    def __init__(
        self,
        group_id: str,
        topics: list[str],
        redis_url: str | None = None,
        message_handler: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        consumer_name: str | None = None,
        **kwargs: Any,
    ):
        self._settings = get_settings()
        self.group_id = group_id
        self.topics = topics
        self._redis_url = redis_url or self._settings.redis_url
        self._message_handler = message_handler
        self._consumer_name = consumer_name or f"{group_id}-{id(self)}"
        self._extra_config = kwargs
        self._redis = None
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._running:
            return

        from core.messaging.redis.connection import create_redis_client
        self._redis = await create_redis_client(url=self._redis_url, **self._extra_config)

        for topic in self.topics:
            try:
                await self._redis.xgroup_create(topic, self.group_id, id="0", mkstream=True)
            except Exception as e:
                if "BUSYGROUP" not in str(e):
                    raise

        self._running = True
        self._task = asyncio.create_task(self._consume_loop())
        logger.info(f"Redis consumer '{self.group_id}' started, streams: {self.topics}")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._redis:
            await self._redis.close()
            self._redis = None
        logger.info(f"Redis consumer '{self.group_id}' stopped")

    def is_running(self) -> bool:
        return self._running

    async def _consume_loop(self) -> None:
        streams = {topic: ">" for topic in self.topics}
        while self._running:
            try:
                messages = await self._redis.xreadgroup(
                    self.group_id,
                    self._consumer_name,
                    streams,
                    count=self._settings.redis_consumer_count,
                    block=self._settings.redis_consumer_block_ms,
                )
                if not messages:
                    continue
                for stream, entries in messages:
                    for entry_id, entry_data in entries:
                        try:
                            await self._process_entry(stream, entry_id, entry_data)
                            await self._redis.xack(stream, self.group_id, entry_id)
                        except Exception as e:
                            logger.error(f"Error processing message: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Consumer loop error: {e}")
                await asyncio.sleep(1)

    async def _process_entry(self, stream: str, entry_id: str, entry_data: dict) -> None:
        data_str = entry_data.get(b"data") or entry_data.get("data")
        if isinstance(data_str, bytes):
            data_str = data_str.decode("utf-8")
        message = json.loads(data_str) if data_str else {}

        headers_str = entry_data.get(b"headers") or entry_data.get("headers")
        if headers_str:
            if isinstance(headers_str, bytes):
                headers_str = headers_str.decode("utf-8")
            headers = json.loads(headers_str)
        else:
            headers = None

        key = entry_data.get(b"key") or entry_data.get("key")
        if isinstance(key, bytes):
            key = key.decode("utf-8")

        stream_name = stream.decode("utf-8") if isinstance(stream, bytes) else stream
        parts = entry_id.split("-") if isinstance(entry_id, str) else entry_id.decode().split("-")
        offset = int(parts[0]) if parts else 0

        from core.messaging.tracking import track_incoming
        await track_incoming(
            topic=stream_name,
            partition=0,
            offset=offset,
            message=message,
            headers=headers,
            key=key,
            worker_id=self.group_id,
        )

        await self.process_message(message)

    async def process_message(self, message: dict[str, Any]) -> None:
        if self._message_handler:
            await self._message_handler(message)
            return

        event_name = message.get("name")
        if not event_name:
            return

        event = Event.from_dict(message)
        handlers = get_event_handlers(event_name)

        for handler in handlers:
            try:
                if handler.consumer_class:
                    instance = handler.consumer_class()
                    method = getattr(instance, handler.method_name)
                    await method(event, None)
                else:
                    await handler.handler(event, None)
            except Exception as e:
                logger.error(f"Handler error for {event_name}: {e}")
