"""Redis Streams producer."""

from __future__ import annotations

from typing import Any
import json

from core.messaging.base import Producer, Event
from core.config import get_settings


class RedisProducer(Producer):
    """Redis Streams producer with automatic event tracking."""

    def __init__(self, redis_url: str | None = None, **kwargs: Any):
        self._settings = get_settings()
        self._redis_url = redis_url or self._settings.redis_url
        self._extra_config = kwargs
        self._redis = None
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        from core.messaging.redis.connection import create_redis_client
        self._redis = await create_redis_client(url=self._redis_url, **self._extra_config)
        self._started = True

    async def stop(self) -> None:
        if self._redis and self._started:
            await self._redis.close()
            self._started = False

    async def send(
        self,
        topic: str,
        message: dict[str, Any],
        key: str | None = None,
        headers: dict[str, str] | None = None,
        wait: bool | None = None,
    ) -> Any:
        if not self._started:
            await self.start()

        from core.messaging.tracking import track_outgoing, track_sent
        event_id, headers = await track_outgoing(topic, message, headers, key)

        entry = {"data": json.dumps(message)}
        if key:
            entry["key"] = key
        if headers:
            entry["headers"] = json.dumps(headers)

        result = await self._redis.xadd(
            topic, entry, maxlen=self._settings.redis_stream_max_len, approximate=True
        )

        if event_id and result:
            parts = result.decode().split("-") if isinstance(result, bytes) else str(result).split("-")
            await track_sent(event_id, 0, int(parts[0]) if parts else 0)

        return result

    async def send_event(self, topic: str, event: Event, key: str | None = None) -> None:
        headers = {"event_name": event.name, "event_id": event.id, "event_source": event.source}
        await self.send(topic, message=event.to_dict(), key=key, headers=headers)

    async def send_batch(self, topic: str, messages: list[dict[str, Any]], wait: bool | None = None) -> int:
        if not self._started:
            await self.start()
        async with self._redis.pipeline() as pipe:
            for message in messages:
                entry = {"data": json.dumps(message)}
                pipe.xadd(topic, entry, maxlen=self._settings.redis_stream_max_len, approximate=True)
            await pipe.execute()
        return len(messages)
