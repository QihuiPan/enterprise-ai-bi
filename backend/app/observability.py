from __future__ import annotations

import json
import logging
import re
import sys
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp

access_logger = logging.getLogger("enterprise_ai_bi.access")
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_ACCESS_HANDLER_MARKER = "_enterprise_ai_bi_access_handler"
_METRIC_METHODS = frozenset(
    {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}
)


def configure_access_logging() -> None:
    """Emit production access events as raw, single-line JSON on stdout."""

    access_logger.setLevel(logging.INFO)
    access_logger.propagate = False
    if any(
        getattr(handler, _ACCESS_HANDLER_MARKER, False)
        for handler in access_logger.handlers
    ):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    setattr(handler, _ACCESS_HANDLER_MARKER, True)
    access_logger.addHandler(handler)


configure_access_logging()


def _request_id(request: Request) -> str:
    supplied = request.headers.get("X-Request-ID", "")
    if _REQUEST_ID_PATTERN.fullmatch(supplied):
        return supplied
    return uuid.uuid4().hex


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a safe request ID and emit one structured access event per request."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = _request_id(request)
        request.state.request_id = request_id
        started_at = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 3)
            event = {
                "timestamp": datetime.now(UTC).isoformat(),
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "client_ip": request.client.host if request.client else None,
            }
            access_logger.info(json.dumps(event, separators=(",", ":")))


@dataclass
class _RequestAggregate:
    count: int = 0
    duration_seconds: float = 0.0


class PrometheusMetrics:
    def __init__(self) -> None:
        self._requests: dict[tuple[str, str, int], _RequestAggregate] = defaultdict(
            _RequestAggregate
        )
        self._in_flight = 0
        self._lock = threading.Lock()

    def started(self) -> None:
        with self._lock:
            self._in_flight += 1

    def completed(
        self, *, method: str, path: str, status_code: int, duration_seconds: float
    ) -> None:
        normalized_method = method.upper()
        if normalized_method not in _METRIC_METHODS:
            normalized_method = "OTHER"
        with self._lock:
            aggregate = self._requests[(normalized_method, path, status_code)]
            aggregate.count += 1
            aggregate.duration_seconds += duration_seconds
            self._in_flight -= 1

    def render(self) -> str:
        with self._lock:
            request_rows = [
                (labels, aggregate.count, aggregate.duration_seconds)
                for labels, aggregate in self._requests.items()
            ]
            in_flight = self._in_flight

        lines = [
            "# HELP enterprise_ai_bi_http_requests_total Total HTTP requests.",
            "# TYPE enterprise_ai_bi_http_requests_total counter",
        ]
        for (method, path, status), count, _ in sorted(request_rows):
            labels = _labels(method=method, path=path, status=str(status))
            lines.append(f"enterprise_ai_bi_http_requests_total{{{labels}}} {count}")
        lines.extend(
            [
                "# HELP enterprise_ai_bi_http_request_duration_seconds HTTP request duration.",
                "# TYPE enterprise_ai_bi_http_request_duration_seconds summary",
            ]
        )
        for (method, path, status), count, duration in sorted(request_rows):
            labels = _labels(method=method, path=path, status=str(status))
            lines.append(
                f"enterprise_ai_bi_http_request_duration_seconds_count{{{labels}}} {count}"
            )
            lines.append(
                "enterprise_ai_bi_http_request_duration_seconds_sum"
                f"{{{labels}}} {duration:.9f}"
            )
        lines.extend(
            [
                "# HELP enterprise_ai_bi_http_requests_in_flight Current HTTP requests.",
                "# TYPE enterprise_ai_bi_http_requests_in_flight gauge",
                f"enterprise_ai_bi_http_requests_in_flight {in_flight}",
                "",
            ]
        )
        return "\n".join(lines)


class MetricsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, registry: PrometheusMetrics) -> None:
        super().__init__(app)
        self.registry = registry

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        self.registry.started()
        started_at = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            # A fixed fallback prevents arbitrary 404 paths from creating
            # unbounded Prometheus label cardinality.
            route_path = getattr(route, "path", None) or "unmatched"
            self.registry.completed(
                method=request.method,
                path=route_path,
                status_code=status_code,
                duration_seconds=time.perf_counter() - started_at,
            )


def _labels(**values: str) -> str:
    return ",".join(
        f'{name}="{_escape_label(value)}"' for name, value in sorted(values.items())
    )


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
