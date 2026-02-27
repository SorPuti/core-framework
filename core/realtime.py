"""
Real-time communication primitives: WebSocket views, SSE views, and Channel hub.

Provides plug-and-play base classes that integrate with the core-framework
view/routing system — including ``permission_classes`` — while bypassing the
HTTP-only middleware stack for WebSocket connections.

Quick start — WebSocket (public)::

    from core import WebSocketView

    class TickStream(WebSocketView):
        async def on_connect(self, ws, **params):
            self.symbol = params.get("symbol", "R_100")

        async def on_receive(self, ws, data):
            await ws.send_json({"echo": data})

Quick start — WebSocket (protected)::

    from core import WebSocketView, IsAuthenticated

    class PrivateStream(WebSocketView):
        permission_classes = [IsAuthenticated]

        async def on_connect(self, ws, **params):
            # self.user is set automatically after auth
            self.room = params["room"]

Quick start — SSE (protected)::

    from core import SSEView, IsAuthenticated

    class TradeEvents(SSEView):
        permission_classes = [IsAuthenticated]

        async def stream(self, request, **params):
            yield {"event": "trade", "data": {"price": 1.23}}

Quick start — Channel (pub/sub fan-out)::

    from core import Channel

    ticks = Channel(maxlen=500)
    await ticks.publish({"price": 1.23})

    async for msg in ticks.subscribe():
        await ws.send_json(msg)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, ClassVar, TYPE_CHECKING

from starlette.websockets import WebSocket, WebSocketState, WebSocketDisconnect
from starlette.requests import Request
from starlette.responses import StreamingResponse
from starlette.routing import WebSocketRoute, Route

if TYPE_CHECKING:
    from core.permissions import Permission

logger = logging.getLogger("core.realtime")


# =============================================================================
# Auth helpers — extract token from WebSocket / SSE request
# =============================================================================

async def _authenticate_ws(ws: WebSocket) -> Any | None:
    """
    Extract a Bearer token from a WebSocket connection and return the
    authenticated user, or ``None`` if no valid credentials are found.

    Token resolution order:
      1. ``Authorization`` header  (``Bearer <token>``)
      2. ``?token=<token>`` query parameter (useful for browser clients
         that cannot set custom headers on WebSocket)
    """
    from core.dependencies import _token_decoder, _user_loader

    if _user_loader is None:
        return None

    token: str | None = None

    auth_header = ws.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()

    if not token:
        token = ws.query_params.get("token")

    if not token:
        return None

    try:
        if _token_decoder is not None:
            payload = _token_decoder(token)
            user_id = payload.get("sub") or payload.get("user_id")
        else:
            user_id = token

        if user_id is None:
            return None

        return await _user_loader(user_id)
    except Exception:
        logger.debug("WebSocket token validation failed", exc_info=True)
        return None


async def _authenticate_request(request: Request) -> Any | None:
    """
    Return the authenticated user from a regular HTTP request.

    Checks ``request.user`` (Starlette middleware) and ``request.state.user``
    (legacy / dependency-injected).  Falls back to manual token extraction
    from the ``Authorization`` header or ``?token=`` query param.
    """
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return user._user if hasattr(user, "_user") else user

    if hasattr(request, "state"):
        state_user = getattr(request.state, "user", None)
        if state_user is not None:
            return state_user

    from core.dependencies import _token_decoder, _user_loader
    if _user_loader is None:
        return None

    token: str | None = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.query_params.get("token")
    if not token:
        return None

    try:
        if _token_decoder is not None:
            payload = _token_decoder(token)
            user_id = payload.get("sub") or payload.get("user_id")
        else:
            user_id = token
        if user_id is None:
            return None
        return await _user_loader(user_id)
    except Exception:
        return None


async def _check_ws_permissions(
    permissions: list[Permission],
    ws: WebSocket,
    user: Any | None,
    view: Any | None = None,
) -> str | None:
    """
    Run permission checks against a WebSocket connection.

    Returns an error message string if denied, or ``None`` if all checks pass.
    A lightweight ``_WSRequest`` adapter is used so that existing ``Permission``
    subclasses (which expect a Starlette ``Request``) work unchanged.
    """
    if not permissions:
        return None

    class _State:
        pass

    class _WSRequest:
        """Minimal Request-like adapter for permission checks on WebSocket."""

        def __init__(self, ws: WebSocket, user: Any | None):
            self.headers = ws.headers
            self.query_params = ws.query_params
            self.path_params = ws.path_params or {}
            self.url = ws.url
            self.method = "WEBSOCKET"
            self.state = _State()
            self.state.user = user  # type: ignore[attr-defined]
            self._user_obj = user

        @property
        def user(self):
            return self._user_obj

    fake_request = _WSRequest(ws, user)

    for perm in permissions:
        perm_instance = perm() if isinstance(perm, type) else perm
        try:
            allowed = await perm_instance.has_permission(fake_request, view)  # type: ignore[arg-type]
        except Exception:
            logger.exception("Permission check raised for %s", type(perm_instance).__name__)
            allowed = False
        if not allowed:
            return perm_instance.message
    return None


# =============================================================================
# Channel — lightweight in-process pub/sub
# =============================================================================

class Channel:
    """
    In-process fan-out channel backed by ``asyncio.Queue`` per subscriber.

    Thread-safe for publish; subscribers are async iterators that yield
    messages until the channel is closed or the subscriber disconnects.

    Args:
        maxlen: Maximum queue depth per subscriber.  Slow consumers that
            fall behind will have their oldest messages dropped.
    """

    def __init__(self, maxlen: int = 1000) -> None:
        self._maxlen = maxlen
        self._subscribers: set[asyncio.Queue[Any]] = set()
        self._lock = asyncio.Lock()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    async def publish(self, message: Any) -> int:
        """Broadcast *message* to every active subscriber.  Returns delivery count."""
        delivered = 0
        async with self._lock:
            dead: list[asyncio.Queue[Any]] = []
            for q in self._subscribers:
                try:
                    q.put_nowait(message)
                    delivered += 1
                except asyncio.QueueFull:
                    try:
                        q.get_nowait()
                        q.put_nowait(message)
                        delivered += 1
                    except Exception:
                        dead.append(q)
            for q in dead:
                self._subscribers.discard(q)
        return delivered

    async def subscribe(self) -> AsyncIterator[Any]:
        """Return an async iterator that yields messages from this channel."""
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=self._maxlen)
        async with self._lock:
            self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            async with self._lock:
                self._subscribers.discard(queue)

    async def subscribe_queue(self) -> asyncio.Queue[Any]:
        """Return a raw ``asyncio.Queue`` for manual consumption."""
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=self._maxlen)
        async with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe_queue(self, queue: asyncio.Queue[Any]) -> None:
        """Remove a previously subscribed queue."""
        async with self._lock:
            self._subscribers.discard(queue)


# =============================================================================
# WebSocketView — class-based WebSocket endpoint
# =============================================================================

class WebSocketView:
    """
    Class-based WebSocket endpoint compatible with core-framework routing.

    Subclass and override the lifecycle hooks:

    - ``on_connect(ws, **params)`` — called after ``accept()``.
    - ``on_receive(ws, data)``     — called for each incoming message.
    - ``on_disconnect(ws, code)``  — called on clean or unclean close.

    The view is instantiated **per-connection** (stateful).  After successful
    authentication ``self.user`` is set to the authenticated user model (or
    ``None`` for public endpoints).

    Class attributes:
        permission_classes:  List of ``Permission`` classes.  Default
            ``[AllowAny]`` (no auth required).  Set to ``[IsAuthenticated]``
            to require a valid JWT.
        encoding:     ``"json"`` | ``"text"`` | ``"bytes"`` (default ``"json"``)
        subprotocol:  Optional WebSocket subprotocol to negotiate.
        keepalive:    Seconds between server-side pings (0 = disabled).
    """

    permission_classes: ClassVar[list[type[Permission]]] = []
    encoding: str = "json"
    subprotocol: str | None = None
    keepalive: int = 30

    user: Any | None = None

    # ── lifecycle hooks (override these) ──

    async def on_connect(self, ws: WebSocket, **params: Any) -> None:
        """Called after the WebSocket handshake completes and auth succeeds."""

    async def on_receive(self, ws: WebSocket, data: Any) -> None:
        """Called when a message is received from the client."""

    async def on_disconnect(self, ws: WebSocket, code: int) -> None:
        """Called when the connection is closed."""

    # ── internal machinery ──

    async def _handle(self, ws: WebSocket) -> None:
        params = ws.path_params or {}

        if self.permission_classes:
            self.user = await _authenticate_ws(ws)
            denied = await _check_ws_permissions(
                self.permission_classes, ws, self.user, self
            )
            if denied:
                await ws.close(code=4003, reason=denied)
                return

        await ws.accept(subprotocol=self.subprotocol)

        try:
            await self.on_connect(ws, **params)
        except Exception:
            logger.exception("WebSocketView.on_connect error")
            await ws.close(code=1011)
            return

        keepalive_task: asyncio.Task[None] | None = None
        if self.keepalive > 0:
            keepalive_task = asyncio.create_task(
                self._keepalive_loop(ws), name="ws-keepalive"
            )

        code = 1000
        try:
            while True:
                data = await self._receive(ws)
                await self.on_receive(ws, data)
        except WebSocketDisconnect as exc:
            code = exc.code
        except Exception:
            code = 1011
            logger.exception("WebSocketView.on_receive error")
        finally:
            if keepalive_task:
                keepalive_task.cancel()
            try:
                await self.on_disconnect(ws, code)
            except Exception:
                logger.exception("WebSocketView.on_disconnect error")
            if ws.client_state == WebSocketState.CONNECTED:
                try:
                    await ws.close(code=code)
                except Exception:
                    pass

    async def _receive(self, ws: WebSocket) -> Any:
        if self.encoding == "json":
            return await ws.receive_json()
        elif self.encoding == "bytes":
            return await ws.receive_bytes()
        return await ws.receive_text()

    async def _keepalive_loop(self, ws: WebSocket) -> None:
        try:
            while ws.client_state == WebSocketState.CONNECTED:
                await asyncio.sleep(self.keepalive)
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_json({"type": "ping"})
        except (asyncio.CancelledError, Exception):
            pass

    @classmethod
    def as_route(cls, path: str) -> WebSocketRoute:
        """Convert this view class into a Starlette ``WebSocketRoute``."""

        async def _endpoint(ws: WebSocket) -> None:
            view = cls()
            await view._handle(ws)

        return WebSocketRoute(path, _endpoint, name=cls.__name__)


# =============================================================================
# SSEView — class-based Server-Sent Events endpoint
# =============================================================================

class SSEView:
    """
    Class-based SSE endpoint compatible with core-framework routing.

    Subclass and implement ``stream()`` as an async generator that yields
    dicts with optional keys ``event``, ``data``, ``id``, ``retry``::

        class MyStream(SSEView):
            permission_classes = [IsAuthenticated]

            async def stream(self, request, **params):
                yield {"event": "hello", "data": {"msg": "hi"}}

    After successful authentication ``self.user`` is available inside
    ``stream()``.

    Class attributes:
        permission_classes:  List of ``Permission`` classes.  Default ``[]``
            (public).  The SSE endpoint runs through the normal HTTP
            middleware stack so standard auth middleware also applies.
        ping_interval:  Seconds between ``:ping`` comments (0 = disabled).
        headers:        Extra response headers.
    """

    permission_classes: ClassVar[list[type[Permission]]] = []
    ping_interval: int = 15
    headers: dict[str, str] = {}

    user: Any | None = None

    async def stream(
        self, request: Request, **params: Any
    ) -> AsyncIterator[dict[str, Any]]:
        """Override to yield SSE event dicts."""
        raise NotImplementedError("Subclass must implement stream()")
        yield  # pragma: no cover

    # ── internal machinery ──

    async def _check_auth(self, request: Request) -> str | None:
        """Authenticate and check permissions.  Returns error message or None."""
        if not self.permission_classes:
            return None

        self.user = await _authenticate_request(request)

        class _State:
            pass

        if not hasattr(request, "state"):
            request.state = _State()  # type: ignore[assignment]
        request.state.user = self.user  # type: ignore[attr-defined]

        for perm_cls in self.permission_classes:
            perm = perm_cls() if isinstance(perm_cls, type) else perm_cls
            try:
                allowed = await perm.has_permission(request, self)  # type: ignore[arg-type]
            except Exception:
                logger.exception("SSE permission check raised for %s", type(perm).__name__)
                allowed = False
            if not allowed:
                return perm.message
        return None

    async def _generate(self, request: Request, params: dict[str, Any]):
        denied = await self._check_auth(request)
        if denied:
            yield f"event: error\ndata: {json.dumps({'error': denied})}\n\n"
            return

        yield ": connected\n\n"

        gen = self.stream(request, **params)
        ping_task: asyncio.Task[None] | None = None

        try:
            if self.ping_interval > 0:
                ping_event = asyncio.Event()
                ping_task = asyncio.create_task(
                    self._ping_timer(ping_event), name="sse-ping"
                )

            async for event in gen:
                if await request.is_disconnected():
                    break
                yield self._format_sse(event)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("SSEView.stream error")
        finally:
            if ping_task:
                ping_task.cancel()

    async def _ping_timer(self, event: asyncio.Event) -> None:
        try:
            while True:
                await asyncio.sleep(self.ping_interval)
                event.set()
        except asyncio.CancelledError:
            pass

    @staticmethod
    def _format_sse(event: dict[str, Any]) -> str:
        lines: list[str] = []
        if "event" in event:
            lines.append(f"event: {event['event']}")
        if "id" in event:
            lines.append(f"id: {event['id']}")
        if "retry" in event:
            lines.append(f"retry: {event['retry']}")
        data = event.get("data", "")
        if isinstance(data, (dict, list)):
            data = json.dumps(data, default=str)
        for line in str(data).split("\n"):
            lines.append(f"data: {line}")
        lines.append("")
        lines.append("")
        return "\n".join(lines)

    @classmethod
    def as_route(cls, path: str, **kwargs: Any) -> Route:
        """Convert this view class into a Starlette ``Route`` (GET)."""

        async def _endpoint(request: Request):
            view = cls()
            params = request.path_params or {}
            response_headers = {
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                **view.headers,
            }
            return StreamingResponse(
                view._generate(request, params),
                media_type="text/event-stream",
                headers=response_headers,
            )

        return Route(path, _endpoint, methods=["GET"], name=cls.__name__, **kwargs)


# =============================================================================
# Helpers for functional-style endpoints
# =============================================================================

def sse_response(
    generator: AsyncIterator[dict[str, Any]],
    *,
    headers: dict[str, str] | None = None,
) -> StreamingResponse:
    """
    Wrap an async generator of SSE event dicts into a ``StreamingResponse``.

    Useful when you don't want a full class-based view::

        @router.get("/events")
        async def events(request: Request):
            async def gen():
                yield {"event": "hello", "data": "world"}
            return sse_response(gen())
    """

    async def _stream():
        yield ": connected\n\n"
        async for event in generator:
            yield SSEView._format_sse(event)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            **(headers or {}),
        },
    )
