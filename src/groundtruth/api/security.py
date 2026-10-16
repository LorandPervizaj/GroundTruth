"""API hardening — rate limits, abuse logging, request guards."""

from __future__ import annotations

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from groundtruth.config import get_settings
from groundtruth.logging import get_logger

logger = get_logger(__name__)

limiter = Limiter(key_func=get_remote_address)


def log_api_abuse(
    *,
    reason: str,
    path: str,
    client_ip: str | None = None,
    **extra: object,
) -> None:
    """Log abuse signals without request bodies or user-supplied PII."""
    logger.warning(
        "api_abuse",
        reason=reason,
        path=path,
        client_ip=client_ip,
        **extra,
    )


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    log_api_abuse(
        reason="rate_limit",
        path=request.url.path,
        client_ip=get_remote_address(request),
        limit=str(exc.detail),
    )
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Try again later."},
        headers=getattr(exc, "headers", None) or {},
    )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        settings = get_settings()
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        csp = (
            "default-src 'self'; script-src 'self'; object-src 'none'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
            "form-action 'self'"
        )
        if settings.is_development:
            response.headers.setdefault("Content-Security-Policy-Report-Only", csp)
        else:
            response.headers.setdefault("Content-Security-Policy", csp)
            # HSTS when TLS is terminated at Azure ingress / nginx (VPS).
            if settings.public_base_url.lower().startswith("https://"):
                response.headers.setdefault(
                    "Strict-Transport-Security",
                    "max-age=31536000; includeSubDomains",
                )
        return response


class MaxBodySizeMiddleware:
    """Reject oversized POST/PUT/PATCH bodies before handlers run."""

    _JSON_WRITE_PREFIXES = (
        "/api/events",
        "/api/feedback",
        "/api/alerts",
        "/api/contact",
        "/api/public-report",
        "/api/listing-submissions",
    )

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        if request.method in ("POST", "PUT", "PATCH"):
            path = request.url.path
            if any(path.startswith(prefix) for prefix in self._JSON_WRITE_PREFIXES):
                content_type = (
                    (request.headers.get("content-type") or "").split(";")[0].strip().lower()
                )
                if content_type != "application/json":
                    log_api_abuse(
                        reason="invalid_content_type",
                        path=path,
                        client_ip=get_remote_address(request),
                        content_type=content_type or None,
                    )
                    response = JSONResponse(
                        status_code=415,
                        content={"detail": "Content-Type must be application/json"},
                    )
                    await response(scope, receive, send)
                    return
            max_bytes = get_settings().api_max_body_bytes

            async def reject() -> None:
                log_api_abuse(
                    reason="oversized_payload",
                    path=path,
                    client_ip=get_remote_address(request),
                    max_bytes=max_bytes,
                )
                response = JSONResponse(
                    status_code=413, content={"detail": "Request body too large"}
                )
                await response(scope, receive, send)

            raw = request.headers.get("content-length")
            if raw:
                try:
                    size = int(raw)
                except ValueError:
                    size = 0
                if size > max_bytes:
                    await reject()
                    return

            # Enforce actual bytes before parsers or handlers can allocate an unbounded
            # body or perform writes. Do not retain an unbounded list of empty frames.
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                if len(body) + len(chunk) > max_bytes:
                    await reject()
                    return
                body.extend(chunk)
                if not message.get("more_body", False):
                    break
            replayed = False

            async def replay() -> Message:
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                # Preserve downstream disconnect polling and streaming response behavior.
                return await receive()

            await self.app(scope, replay, send)
            return
        await self.app(scope, receive, send)
