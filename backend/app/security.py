from __future__ import annotations

import math
import secrets
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass

from fastapi import Request
from starlette.datastructures import MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

UPLOAD_BODY_PATHS = {
    "/api/data/upload",
    "/api/data/preview",
    "/api/data/import",
}
MULTIPART_OVERHEAD_BYTES = 256 * 1024


class RequestBodyLimitMiddleware:
    """Bound upload request bodies before multipart parsing can spool them to disk."""

    def __init__(self, app: ASGIApp, *, max_upload_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_upload_bytes + MULTIPART_OVERHEAD_BYTES

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413,
            content={"detail": "Request body exceeds the configured upload limit."},
        )
        await response(scope, receive, send)

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path") not in UPLOAD_BODY_PATHS
        ):
            await self.app(scope, receive, send)
            return

        headers = {
            key.lower(): value for key, value in scope.get("headers", [])
        }
        raw_content_length = headers.get(b"content-length")
        if raw_content_length is not None:
            try:
                if int(raw_content_length) > self.max_body_bytes:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                pass

        received_bytes = 0
        buffered_messages: deque[Message] = deque()
        while True:
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_body_bytes:
                    await self._reject(scope, receive, send)
                    return
            buffered_messages.append(message)
            if message["type"] == "http.disconnect" or not message.get(
                "more_body", False
            ):
                break

        async def replay_receive() -> Message:
            if buffered_messages:
                return buffered_messages.popleft()
            return await receive()

        await self.app(scope, replay_receive, send)


def _is_api_path(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


def _is_api_request(request: Request) -> bool:
    return _is_api_path(request.url.path) and request.method != "OPTIONS"


class NoStoreAPIMiddleware:
    """Prevent browsers and intermediaries from retaining business API data."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http" or not _is_api_path(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        async def send_with_no_store(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_with_no_store)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Require a configured API key for business API routes.

    An empty key disables authentication so a fresh local checkout remains usable.
    System, documentation, and CORS preflight routes remain public.
    """

    def __init__(self, app: ASGIApp, *, api_key: str | None, header_name: str) -> None:
        super().__init__(app)
        self.api_key = api_key
        self.header_name = header_name

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if self.api_key and _is_api_request(request):
            supplied_key = request.headers.get(self.header_name, "")
            if not secrets.compare_digest(supplied_key, self.api_key):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "A valid API key is required."},
                    headers={"WWW-Authenticate": "ApiKey"},
                )
            request.state.rate_limit_identity = "authenticated-api-key"
        return await call_next(request)


@dataclass
class _RateLimitWindow:
    started_at: float
    count: int


class InMemoryRateLimiter:
    """A bounded, process-local fixed-window limiter for a single demo instance."""

    def __init__(self, *, requests: int, window_seconds: int, max_clients: int) -> None:
        self.requests = requests
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self._clients: OrderedDict[str, _RateLimitWindow] = OrderedDict()
        self._lock = threading.Lock()

    def consume(self, client_key: str, now: float | None = None) -> tuple[bool, int, int]:
        current_time = time.monotonic() if now is None else now
        with self._lock:
            window = self._clients.pop(client_key, None)
            if window is None or current_time - window.started_at >= self.window_seconds:
                window = _RateLimitWindow(started_at=current_time, count=0)

            allowed = window.count < self.requests
            if allowed:
                window.count += 1
            self._clients[client_key] = window

            while len(self._clients) > self.max_clients:
                self._clients.popitem(last=False)

            remaining = max(0, self.requests - window.count)
            reset_seconds = max(
                1, math.ceil(self.window_seconds - (current_time - window.started_at))
            )
            return allowed, remaining, reset_seconds

    @property
    def tracked_clients(self) -> int:
        with self._lock:
            return len(self._clients)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        *,
        requests: int,
        window_seconds: int,
        max_clients: int,
    ) -> None:
        super().__init__(app)
        self.limit = requests
        self.limiter = InMemoryRateLimiter(
            requests=requests,
            window_seconds=window_seconds,
            max_clients=max_clients,
        )

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if self.limit == 0 or not _is_api_request(request):
            return await call_next(request)

        client_key = getattr(
            request.state,
            "rate_limit_identity",
            request.client.host if request.client else "unknown",
        )
        allowed, remaining, reset_seconds = self.limiter.consume(client_key)
        headers = {
            "RateLimit-Limit": str(self.limit),
            "RateLimit-Remaining": str(remaining),
            "RateLimit-Reset": str(reset_seconds),
        }
        if not allowed:
            headers["Retry-After"] = str(reset_seconds)
            return JSONResponse(
                status_code=429,
                content={"detail": "Request rate limit exceeded."},
                headers=headers,
            )

        response = await call_next(request)
        response.headers.update(headers)
        return response
