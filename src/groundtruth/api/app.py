"""Metrik API — application composition root."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.staticfiles import StaticFiles

from groundtruth.api.comparables_warm import (
    start_background_comparables_warm,
    stop_background_comparables_warm,
)
from groundtruth.api.corpus_warm import start_background_corpus_warm, stop_background_corpus_warm
from groundtruth.api.deps import DbSession, require_ops_access
from groundtruth.api.reports import router as reports_router
from groundtruth.api.routes_markets import router as markets_router
from groundtruth.api.routes_pages import WEB_DIR, html_page
from groundtruth.api.routes_pages import router as pages_router
from groundtruth.api.routes_product_writes import router as product_writes_router
from groundtruth.api.security import (
    MaxBodySizeMiddleware,
    SecurityHeadersMiddleware,
    limiter,
    rate_limit_exceeded_handler,
)
from groundtruth.api.timing import RequestTimingMiddleware, latency_snapshot
from groundtruth.config import get_settings
from groundtruth.schemas.coverage_analytics import CoverageAnalyticsSnapshot
from groundtruth.schemas.product_analytics import ProductAnalyticsSnapshot
from groundtruth.services.coverage_metrics import coverage_analytics_snapshot
from groundtruth.services.lookup_cache import load_lookup_cache_from_disk
from groundtruth.services.product_metrics import product_analytics_snapshot
from groundtruth.startup import validate_production_settings

logger = logging.getLogger(__name__)


def _trusted_hosts() -> list[str]:
    from urllib.parse import urlparse

    hosts = ["localhost", "127.0.0.1"]
    settings = get_settings()
    if settings.is_development:
        # Starlette TestClient default Host header.
        hosts.append("testserver")
    hostname = urlparse(settings.public_base_url).hostname
    if hostname and hostname not in hosts:
        hosts.append(hostname)
    # Azure Container Apps probes/ingress may use sibling hostnames under the
    # managed environment domain; allow the parent suffix when deployed there.
    if hostname and hostname.endswith(".azurecontainerapps.io"):
        hosts.append(".azurecontainerapps.io")
    extra = (settings.trusted_hosts or "").strip()
    for item in extra.split(","):
        item = item.strip()
        if item and item not in hosts:
            hosts.append(item)
    return hosts


class ProdStaticFiles(StaticFiles):
    """Static assets with cache headers tuned for environment."""

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if response.status_code != 200:
            return response
        settings = get_settings()
        if settings.is_development:
            response.headers["Cache-Control"] = "no-cache"
        else:
            response.headers["Cache-Control"] = "public, max-age=86400"
        return response


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    settings = get_settings()
    validate_production_settings(settings)

    if settings.sentry_dsn:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            integrations=[StarletteIntegration(), FastApiIntegration()],
        )
        logger.info("Sentry error reporting enabled (environment=%s)", settings.app_env)
    elif not settings.is_development:
        logger.warning("SENTRY_DSN is unset — production errors will only appear in container logs")

    if settings.is_development or not settings.api_rate_limit_enabled:
        # Development may disable limits; production refuses this via validate_production_settings.
        limiter.enabled = False

    if not settings.is_development and settings.api_require_lookup_cache:
        from groundtruth.services.artifact_integrity import verify_and_record_release_artifacts

        integrity = await asyncio.to_thread(verify_and_record_release_artifacts)
        if not integrity.verified:
            raise RuntimeError(
                "Production requires verified release artifacts; "
                f"verification failed: {integrity.error}"
            )

    loaded = await asyncio.to_thread(load_lookup_cache_from_disk)
    logger.info("Lookup disk cache loaded: %s entries", loaded)
    if not settings.is_development and settings.api_require_lookup_cache:
        from groundtruth.analytics.valuation import comparables_cache_ready

        if loaded == 0 or not comparables_cache_ready():
            raise RuntimeError(
                "Production requires verified lookup and comparables artifacts; "
                "build and mount the release bundle before startup."
            )
    if loaded == 0:
        start_background_corpus_warm()
        start_background_comparables_warm()
    else:
        from groundtruth.analytics.valuation import comparables_cache_ready

        if not comparables_cache_ready():
            start_background_comparables_warm()
        logger.info("Skipping background corpus warm — serving from precomputed cache")
    yield
    stop_background_comparables_warm()
    stop_background_corpus_warm()


_settings = get_settings()
_docs_enabled = _settings.is_development or _settings.api_docs_enabled
app = FastAPI(
    title="Metrik",
    version="1.3.0",
    lifespan=_lifespan,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(RequestTimingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(MaxBodySizeMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_trusted_hosts())

# CORS: intentionally not configured — same-origin HTML + API. If added later,
# restrict allow_origins to known frontend host(s); never use "*" with credentials.

app.include_router(reports_router)
app.include_router(markets_router)
app.include_router(product_writes_router)
app.include_router(pages_router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if (
        exc.status_code == 404
        and not request.url.path.startswith("/api/")
        and "text/html" in request.headers.get("accept", "")
    ):
        return html_page("404.html", status_code=404)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/api/health")
def liveness_health() -> dict[str, str]:
    """Process liveness probe — always 200 when the app process can serve HTTP.

    Distinct from ``/api/ready`` (release/artifact/DB readiness) and from
    ``/api/health/perf`` (ops-token latency snapshot). Azure Container Apps
    should use this path for liveness and ``/api/ready`` for readiness.
    """
    return {"status": "ok"}


@app.get("/api/health/perf")
def perf_health(request: Request) -> dict:
    """Cold-start and warm-request latency snapshot (ops / profiling)."""
    require_ops_access(request)

    from groundtruth.api.corpus_warm import corpus_warm_state

    warm = corpus_warm_state()
    snap = latency_snapshot()
    return {
        "corpus_warm": {
            "complete": warm.finished_at is not None and warm.error is None,
            "duration_ms": warm.duration_ms,
            "error": warm.error,
            "active_listings": warm.active_listings,
        },
        "warm_requests": {
            "sample_count": snap.sample_count,
            "lookup_p50_ms": snap.warm_lookup_p50_ms,
            "lookup_p95_ms": snap.warm_lookup_p95_ms,
            "valuate_p50_ms": snap.warm_valuate_p50_ms,
            "valuate_p95_ms": snap.warm_valuate_p95_ms,
        },
    }


@app.get("/api/metrics")
def api_metrics(request: Request) -> dict:
    """Basic in-process request counters (lock down in production)."""
    require_ops_access(request)

    from groundtruth.api.metrics import metrics_snapshot

    return metrics_snapshot()


@app.get("/api/analytics/product", response_model=ProductAnalyticsSnapshot)
def product_analytics(
    request: Request,
    session: DbSession,
    days: int = Query(default=30, ge=1, le=365),
) -> ProductAnalyticsSnapshot:
    """Product usage dashboard (ops token required in production)."""
    require_ops_access(request)
    return product_analytics_snapshot(days=days, session=session)


@app.get("/api/analytics/coverage", response_model=CoverageAnalyticsSnapshot)
def coverage_analytics(
    request: Request,
    session: DbSession,
    freshness_days: int = Query(default=14, ge=1, le=90),
) -> CoverageAnalyticsSnapshot:
    """Data coverage KPIs (ops token required in production)."""
    require_ops_access(request)
    return coverage_analytics_snapshot(session, freshness_days=freshness_days)


if WEB_DIR.exists():
    app.mount("/static", ProdStaticFiles(directory=WEB_DIR / "static"), name="static")


# Compatibility façades for tests / callers that imported helpers from this module.
_require_ops_access = require_ops_access
_html_page = html_page
