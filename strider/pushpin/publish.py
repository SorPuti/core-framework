"""
Publicação GRIP no Pushpin via HTTP POST no endpoint ``/publish/``.

Formato alinhado ao [quickstart](https://pushpin.org/docs/getting-started/#quickstart)
e à API de *items* com ``formats.http-stream``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


class PushpinPublishError(RuntimeError):
    """Falha ao publicar no endpoint HTTP do Pushpin."""


def build_http_stream_item(
    channel: str,
    content: str,
    *,
    item_id: str | None = None,
) -> dict[str, Any]:
    """
    Um item no array ``items`` do corpo JSON de ``/publish/`` (formato *http-stream*).

    Args:
        channel: Canal GRIP (o mesmo usado em ``Grip-Channel`` na resposta inicial).
        content: Corpo a enviar aos subscritores (normalmente termina com ``\\n``).
        item_id: Opcional, identificador lógico do item (se suportado pelo broker).
    """
    if not channel or not str(channel).strip():
        raise ValueError("channel must be non-empty")
    item: dict[str, Any] = {
        "channel": str(channel).strip(),
        "formats": {"http-stream": {"content": content}},
    }
    if item_id:
        item["id"] = item_id
    return item


def build_publish_body(items: list[dict[str, Any]]) -> bytes:
    """Serializa o corpo JSON ``{"items": [...]}``."""
    if not items:
        raise ValueError("items must be non-empty")
    return json.dumps({"items": items}, ensure_ascii=False).encode("utf-8")


async def publish_pushpin_items(
    items: list[dict[str, Any]],
    *,
    url: str | None = None,
    timeout: float | None = None,
) -> None:
    """
    Publica uma ou mais mensagens no Pushpin (POST JSON).

    Não exige ``httpx``: usa ``urllib`` em ``asyncio.to_thread``.

    Args:
        items: Lista de dicts (use :func:`build_http_stream_item` ou payload manual).
        url: Sobrepõe ``Settings.pushpin_publish_url``.
        timeout: Sobrepõe ``Settings.pushpin_publish_timeout``.
    """
    try:
        from strider.config import get_settings

        s = get_settings()
        publish_url = url or getattr(
            s, "pushpin_publish_url", "http://127.0.0.1:5561/publish/"
        )
        t = timeout if timeout is not None else float(
            getattr(s, "pushpin_publish_timeout", 5.0)
        )
    except Exception:
        publish_url = url or "http://127.0.0.1:5561/publish/"
        t = float(timeout if timeout is not None else 5.0)

    body = build_publish_body(items)

    def _post() -> tuple[int, str]:
        req = urllib.request.Request(
            publish_url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        with urllib.request.urlopen(req, timeout=t) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            msg = (resp.read() or b"").decode("utf-8", errors="replace")[:500]
            return int(code), msg

    try:
        code, _msg = await asyncio.to_thread(_post)
        if code >= 400:
            raise PushpinPublishError(
                f"Pushpin publish returned HTTP {code} at {publish_url!r}"
            )
    except PushpinPublishError:
        raise
    except urllib.error.HTTPError as e:
        raise PushpinPublishError(
            f"Pushpin publish HTTP {e.code}: {e.reason!r} ({publish_url})"
        ) from e
    except urllib.error.URLError as e:
        raise PushpinPublishError(
            f"Pushpin publish connection failed ({publish_url}): {e.reason!r}"
        ) from e
    except Exception as e:
        raise PushpinPublishError(f"Pushpin publish failed: {e}") from e

    logger.debug("Pushpin publish OK: %d item(s) -> %s", len(items), publish_url)


async def publish_http_stream(
    channel: str,
    content: str,
    *,
    url: str | None = None,
    timeout: float | None = None,
    item_id: str | None = None,
) -> None:
    """Atalho: um único item *http-stream*."""
    await publish_pushpin_items(
        [build_http_stream_item(channel, content, item_id=item_id)],
        url=url,
        timeout=timeout,
    )


__all__ = [
    "PushpinPublishError",
    "build_http_stream_item",
    "build_publish_body",
    "publish_pushpin_items",
    "publish_http_stream",
]
