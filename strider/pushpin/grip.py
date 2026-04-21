"""
Cabeçalhos GRIP para respostas atrás do [Pushpin](https://pushpin.org/docs/getting-started/#quickstart).

O backend (FastAPI/Strider) devolve instruções `Grip-*`; o Pushpin mantém a ligação
HTTP/WebSocket e encaminha eventos publicados no canal.
"""

from __future__ import annotations

from starlette.responses import Response

# Nomes dos cabeçalhos GRIP (Fanout / Pushpin)
GRIP_HOLD = "Grip-Hold"
GRIP_CHANNEL = "Grip-Channel"
GRIP_TIMEOUT = "Grip-Timeout"
GRIP_SET_META = "Grip-Set-Meta"

# Valores comuns de Grip-Hold
HOLD_STREAM = "stream"
HOLD_RESPONSE = "response"


def qualify_channel(name: str, *, prefix: str = "") -> str:
    """
    Junta prefixo opcional (ex.: ``Settings.pushpin_default_channel_prefix``) ao canal.
    """
    n = (name or "").strip()
    p = (prefix or "").strip().rstrip(".")
    if not n:
        raise ValueError("channel name must be non-empty")
    if p:
        return f"{p}.{n}"
    return n


def qualify_channel_from_settings(name: str) -> str:
    """Aplica ``pushpin_default_channel_prefix`` das settings ao nome lógico."""
    try:
        from strider.config import get_settings

        pfx = getattr(get_settings(), "pushpin_default_channel_prefix", "") or ""
    except Exception:
        pfx = ""
    return qualify_channel(name, prefix=pfx)


def grip_stream_headers(
    channel: str,
    *,
    hold: str = HOLD_STREAM,
    timeout: str | None = None,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """
    Cabeçalhos mínimos para *HTTP streaming* via Pushpin (equivalente ao quickstart).

    Args:
        channel: Nome lógico do canal GRIP (ex.: ``test``, ``user-123-updates``).
        hold: Valor de ``Grip-Hold`` (por omissão ``stream``).
        timeout: Opcional: valor de ``Grip-Timeout``.
        extra: Cabeçalhos GRIP adicionais (ex.: ``Grip-Set-Meta``).

    Returns:
        Dict pronto para passar a ``Response(..., headers=)``.
    """
    if not channel or not channel.strip():
        raise ValueError("Grip-Channel must be non-empty")
    h: dict[str, str] = {
        GRIP_HOLD: hold,
        GRIP_CHANNEL: channel.strip(),
    }
    if timeout:
        h[GRIP_TIMEOUT] = timeout
    if extra:
        h.update({k: v for k, v in extra.items() if v is not None})
    return h


def grip_stream_response(
    channel: str,
    *,
    status_code: int = 200,
    content: bytes | str = "",
    media_type: str | None = "text/plain; charset=utf-8",
    hold: str = HOLD_STREAM,
    timeout: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> Response:
    """
    :class:`starlette.responses.Response` com GRIP para subscrição *stream*.

    O corpo inicial pode ser vazio; o conteúdo em tempo real chega via *publish*.
    """
    headers = grip_stream_headers(
        channel, hold=hold, timeout=timeout, extra=extra_headers
    )
    body = content.encode("utf-8") if isinstance(content, str) else content
    return Response(
        status_code=status_code,
        content=body,
        media_type=media_type,
        headers=headers,
    )


def grip_response_hold_headers(
    channel: str,
    *,
    timeout: str | None = None,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """Cabeçalhos para ``Grip-Hold: response`` (long-polling / resposta adiada)."""
    return grip_stream_headers(
        channel, hold=HOLD_RESPONSE, timeout=timeout, extra=extra
    )


def merge_grip_into_response_headers(
    response: Response,
    grip: dict[str, str],
) -> Response:
    """
    Junta cabeçalhos GRIP a uma resposta já construída (útil com JSONResponse).

    Devolve a mesma instância com ``response.headers`` actualizado.
    """
    for k, v in grip.items():
        response.headers[k] = v
    return response


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
    "grip_stream_response",
    "grip_response_hold_headers",
    "merge_grip_into_response_headers",
]
