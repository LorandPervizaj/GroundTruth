"""API hardening — rate limits, abuse logging, request guards."""

from __future__ import annotations

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

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


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Reject oversized POST/PUT/PATCH bodies before handlers run."""

    _JSON_WRITE_PREFIXES = (
        "/api/events",
        "/api/feedback",
        "/api/alerts",
        "/api/contact",
        "/api/public-report",
        "/api/listing-submissions",
    )

    async def dispatch(self, request: Request, call_next):
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
                    return JSONResponse(
                        status_code=415,
                        content={"detail": "Content-Type must be application/json"},
                    )
            raw = request.headers.get("content-length")
            if raw:
                try:
                    size = int(raw)
                except ValueError:
                    size = 0
                max_bytes = get_settings().api_max_body_bytes
                if size > max_bytes:
                    log_api_abuse(
                        reason="oversized_payload",
                        path=request.url.path,
                        client_ip=get_remote_address(request),
                        content_length=size,
                        max_bytes=max_bytes,
                    )
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Request body too large"},
                    )
        return await call_next(request)
