from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.websockets import WebSocketState

from strider.realtime import WebSocketView


def _build_ws_mock() -> MagicMock:
    ws = MagicMock()
    ws.path_params = {}
    ws.client_state = WebSocketState.CONNECTED
    ws.application_state = WebSocketState.CONNECTED

    async def _close(*args, **kwargs):
        ws.client_state = WebSocketState.DISCONNECTED
        ws.application_state = WebSocketState.DISCONNECTED

    ws.accept = AsyncMock()
    ws.close = AsyncMock(side_effect=_close)
    ws.receive_json = AsyncMock(
        side_effect=RuntimeError('WebSocket is not connected. Need to call "accept" first.')
    )
    return ws


@pytest.mark.asyncio
async def test_handle_skips_receive_when_closed_in_on_connect():
    class ClosingOnConnectView(WebSocketView):
        keepalive = 0

        def __init__(self):
            super().__init__()
            self.disconnect_code = None

        async def on_connect(self, ws, **params):
            await ws.close(code=4404)

        async def on_disconnect(self, ws, code):
            self.disconnect_code = code

    view = ClosingOnConnectView()
    ws = _build_ws_mock()

    await view._handle(ws)

    ws.accept.assert_awaited_once()
    ws.receive_json.assert_not_awaited()
    assert view.disconnect_code == 1000
