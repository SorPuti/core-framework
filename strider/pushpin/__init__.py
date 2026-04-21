"""
Integração opcional com [Pushpin](https://pushpin.org/docs/getting-started/#quickstart)
(proxy GRIP na borda para push HTTP/WebSocket).

- **Resposta**: cabeçalhos ``Grip-Hold`` / ``Grip-Channel`` (:mod:`strider.pushpin.grip`).
- **Publicar**: POST JSON no controlo Pushpin (:mod:`strider.pushpin.publish`).

Configuração típica (``routes`` do Pushpin a apontar para a app Strider, ex. ``* localhost:8000``).
"""

from strider.pushpin.grip import (
    GRIP_CHANNEL,
    GRIP_HOLD,
    GRIP_SET_META,
    GRIP_TIMEOUT,
    HOLD_RESPONSE,
    HOLD_STREAM,
    grip_response_hold_headers,
    grip_stream_headers,
    grip_stream_response,
    merge_grip_into_response_headers,
    qualify_channel,
    qualify_channel_from_settings,
)
from strider.pushpin.publish import (
    PushpinPublishError,
    build_http_stream_item,
    build_publish_body,
    publish_http_stream,
    publish_pushpin_items,
)

__all__ = [
    "GRIP_HOLD",
    "GRIP_CHANNEL",
    "GRIP_TIMEOUT",
    "GRIP_SET_META",
    "HOLD_STREAM",
    "HOLD_RESPONSE",
    "qualify_channel",
    "qualify_channel_from_settings",
    "grip_stream_headers",
    "grip_response_hold_headers",
    "grip_stream_response",
    "merge_grip_into_response_headers",
    "PushpinPublishError",
    "build_http_stream_item",
    "build_publish_body",
    "publish_pushpin_items",
    "publish_http_stream",
]
