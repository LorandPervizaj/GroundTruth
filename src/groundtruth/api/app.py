"""Metrik API — market lookup + rent valuation."""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from pydantic import BaseModel
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.staticfiles import StaticFiles

from groundtruth.analytics.valuation import (
    INSUFFICIENT_EVIDENCE_MSG,
    estimate_valuation,
    list_neighborhood_options,
)
from groundtruth.api.comparables_warm import start_background_comparables_warm
from groundtruth.api.corpus_warm import start_background_corpus_warm
from groundtruth.api.reports import router as reports_router
from groundtruth.api.security import (
    MaxBodySizeMiddleware,
    SecurityHeadersMiddleware,
    limiter,
    log_api_abuse,
    rate_limit_exceeded_handler,
)
from groundtruth.api.timing import RequestTimingMiddleware, latency_snapshot
from groundtruth.config import PROJECT_ROOT, get_settings
from groundtruth.database.session import get_session, get_session_factory
from groundtruth.schemas.alerts import SavedAlertRequest
from groundtruth.schemas.budget_match import BudgetMatchRequest, BudgetMatchResponse
from groundtruth.schemas.changelog import ChangelogCategory, ChangelogResponse
from groundtruth.schemas.contact import (
    ContactRequest,
    ListingSubmissionRequest,
    PublicReportRequest,
)
from groundtruth.schemas.coverage_analytics import CoverageAnalyticsSnapshot
from groundtruth.schemas.feedback import DataFeedbackRequest
from groundtruth.schemas.lookup import (
    CompareResponse,
    CorpusMeta,
    MarketHistory,
    NeighborhoodMarketSummary,
    SearchResponse,
)
from groundtruth.schemas.methodology import MethodologyPublic
from groundtruth.schemas.product_analytics import ProductAnalyticsSnapshot, ProductEvent
from groundtruth.schemas.valuation import (
    NeighborhoodOption,
    ValuationRequest,
    ValuationResult,
)
from groundtruth.services.alerts import log_price_alert
from groundtruth.services.budget_match import budget_match
from groundtruth.services.changelog_public import load_public_changelog
from groundtruth.services.coverage_metrics import coverage_analytics_snapshot
from groundtruth.services.feedback import log_data_feedback
from groundtruth.services.lookup import (
    compare_neighborhoods,
    get_corpus_meta,
    get_market_history,
    list_neighborhood_market_summaries,
)
from groundtruth.services.lookup_cache import (
    corpus_meta_from_cache,
    load_lookup_cache_from_disk,
    resolve_market_lookup,
)
from groundtruth.services.methodology_public import get_public_methodology
from groundtruth.services.product_analytics import log_product_event
from groundtruth.services.product_metrics import product_analytics_snapshot
from groundtruth.services.product_submissions import append_product_submission
from groundtruth.services.rent_yield import (
    build_rent_yield_from_lookup_cache,
    build_rent_yield_table,
    load_rent_yield_cache,
)
from groundtruth.services.search import search_market
from groundtruth.services.web_shell import (
    inject_accessibility_shell,
    inject_canonical_url,
    inject_sanitize_script,
    inject_site_footer,
    inject_static_asset_hashes,
)
from groundtruth.startup import validate_production_settings

WEB_DIR = PROJECT_ROOT / "web"
_STATIC_PAGE_PATHS = {
    "index.html": "/",
    "valuate.html": "/valuate",
    "find.html": "/find",
    "statistics.html": "/statistics",
    "compare.html": "/compare",
    "rent-yield.html": "/rent-yield",
    "contact.html": "/contact",
    "changelog.html": "/changelog",
    "alerts.html": "/alerts",
    "methodology.html": "/methodology",
    "privacy.html": "/privacy",
    "terms.html": "/terms",
}
EntityType = Literal["neighborhood", "district", "street", "complex"]
logger = logging.getLogger(__name__)
DbSession = Annotated[Session, Depends(get_session)]


def _require_ops_access(request: Request) -> None:
    """Hide operational endpoints unless the configured token matches."""
    settings = get_settings()
    if settings.is_development:
        return
    expected = settings.health_check_token
    provided = request.headers.get("X-Health-Token")
    if not expected or not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=404, detail="Not found")


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
    return hosts


def _html_page(filename: str, *, status_code: int = 200) -> HTMLResponse:
    body = inject_site_footer((WEB_DIR / filename).read_text(encoding="utf-8"))
    body = inject_static_asset_hashes(body)
    body = inject_sanitize_script(body)
    body = inject_accessibility_shell(body)
    page_path = _STATIC_PAGE_PATHS.get(filename)
    if page_path is not None:
        base_url = get_settings().public_base_url.rstrip("/")
        body = inject_canonical_url(body, f"{base_url}{page_path}")
    return HTMLResponse(
        content=body,
        status_code=status_code,
        headers={"Cache-Control": "no-cache"},
    )


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

    if settings.is_development or not settings.api_rate_limit_enabled:
        limiter.enabled = False

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


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if (
        exc.status_code == 404
        and not request.url.path.startswith("/api/")
        and "text/html" in request.headers.get("accept", "")
    ):
        return _html_page("404.html", status_code=404)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


class LangPreference(BaseModel):
    lang: Literal["sq", "en"]


def _rate_limit(limit_key: str):
    """Resolve per-route limit string from settings at request time."""
    return lambda: getattr(get_settings(), limit_key)


def _set_public_cache(response: Response, *, max_age: int = 60) -> None:
    """Allow short browser/CDN caching for stable aggregate GET payloads."""
    response.headers["Cache-Control"] = f"public, max-age={max_age}"
    response.headers["Vary"] = "Accept-Encoding"


@app.get("/api/neighborhoods", response_model=list[NeighborhoodOption])
def neighborhoods(response: Response, session: DbSession) -> list[NeighborhoodOption]:
    from groundtruth.services.lookup_cache import cache_is_loaded, get_cached_neighborhood_options

    _set_public_cache(response, max_age=120)
    if cache_is_loaded():
        rows = get_cached_neighborhood_options()
        if rows:
            return [NeighborhoodOption.model_validate(row) for row in rows]
    rows = list_neighborhood_options(session)
    return [NeighborhoodOption.model_validate(row) for row in rows]


@app.get("/api/methodology", response_model=MethodologyPublic)
def methodology_meta(session: DbSession) -> MethodologyPublic:
    return get_public_methodology(session)


@app.get("/api/meta", response_model=CorpusMeta)
def corpus_meta(response: Response, session: DbSession) -> CorpusMeta:
    _set_public_cache(response, max_age=60)
    cached = corpus_meta_from_cache(session)
    if cached is not None:
        return cached
    return get_corpus_meta(session)


@app.get("/api/ready")
def api_ready(request: Request) -> dict:
    from groundtruth.analytics.valuation import comparables_cache_ready
    from groundtruth.services.lookup_cache import cache_is_loaded

    settings = get_settings()
    lookup_cache = cache_is_loaded()
    comparables_ready = comparables_cache_ready()
    ok = True
    if not settings.is_development and settings.api_require_lookup_cache:
        ok = lookup_cache and comparables_ready
    payload: dict[str, object] = {"ok": ok}
    if settings.is_development:
        payload.update(
            {
                "environment": settings.app_env,
                "lookup_cache": lookup_cache,
                "comparables_ready": comparables_ready,
            }
        )
    else:
        expected = settings.health_check_token
        provided = request.headers.get("X-Health-Token")
        if expected and provided and secrets.compare_digest(provided, expected):
            payload.update(
                {
                    "environment": settings.app_env,
                    "lookup_cache": lookup_cache,
                    "comparables_ready": comparables_ready,
                }
            )
    return payload


@app.get("/api/health/perf")
def perf_health(request: Request) -> dict:
    """Cold-start and warm-request latency snapshot (ops / profiling)."""
    _require_ops_access(request)

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
    _require_ops_access(request)

    from groundtruth.api.metrics import metrics_snapshot

    return metrics_snapshot()


@app.get("/api/analytics/product", response_model=ProductAnalyticsSnapshot)
def product_analytics(
    request: Request,
    session: DbSession,
    days: int = Query(default=30, ge=1, le=365),
) -> ProductAnalyticsSnapshot:
    """Product usage dashboard (ops token required in production)."""
    _require_ops_access(request)
    return product_analytics_snapshot(days=days, session=session)


@app.get("/api/analytics/coverage", response_model=CoverageAnalyticsSnapshot)
def coverage_analytics(
    request: Request,
    session: DbSession,
    freshness_days: int = Query(default=14, ge=1, le=90),
) -> CoverageAnalyticsSnapshot:
    """Data coverage KPIs (ops token required in production)."""
    _require_ops_access(request)
    return coverage_analytics_snapshot(session, freshness_days=freshness_days)


@app.get("/api/markets", response_model=list[NeighborhoodMarketSummary])
def markets(response: Response, session: DbSession) -> list[NeighborhoodMarketSummary]:
    from groundtruth.services.lookup_cache import cache_is_loaded, get_cached_markets

    _set_public_cache(response, max_age=120)
    if cache_is_loaded():
        return get_cached_markets()
    return list_neighborhood_market_summaries(session)


@app.get("/api/rent-yield")
def rent_yield(response: Response) -> dict:
    """Neighborhood gross rent yield where rent and sale samples are sufficient."""
    from groundtruth.services.lookup_cache import cache_is_loaded

    _set_public_cache(response, max_age=120)
    if cache_is_loaded():
        rows = build_rent_yield_from_lookup_cache()
        if rows:
            return {"rows": rows, "cached": True}

    cached = load_rent_yield_cache()
    if cached:
        return {"rows": cached, "cached": True}

    session = get_session_factory()()
    try:
        rows = build_rent_yield_table(session)
    except Exception as exc:
        logger.exception("rent_yield_database_error")
        raise HTTPException(
            status_code=503,
            detail="Rent-yield data is temporarily unavailable.",
        ) from exc
    finally:
        session.close()

    if rows:
        return {"rows": rows}
    return {"rows": []}


@app.get("/api/search", response_model=SearchResponse)
async def search(
    request: Request,
    q: str = Query(min_length=1),
) -> SearchResponse:
    settings = get_settings()
    if len(q) > settings.api_search_max_length:
        raise HTTPException(
            status_code=400,
            detail=f"Query must be at most {settings.api_search_max_length} characters",
        )
    from groundtruth.services.lookup_cache import cache_is_loaded

    if not settings.is_development and settings.api_require_lookup_cache and not cache_is_loaded():
        raise HTTPException(status_code=503, detail="Search cache unavailable")

    def _run_search() -> SearchResponse:
        session = get_session_factory()()
        try:
            return search_market(session, q)
        finally:
            session.close()

    try:
        t0 = time.perf_counter()
        result = await asyncio.wait_for(
            asyncio.to_thread(_run_search),
            timeout=settings.api_search_timeout_sec,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        n_results = len(result.results)
        log_product_event(
            ProductEvent(
                event="search_performed",
                query_length=len(q),
                results_count=n_results,
                section="api",
                response_time_ms=round(elapsed_ms, 1),
            ),
            request,
        )
        if n_results == 0:
            log_product_event(
                ProductEvent(
                    event="zero_results",
                    query_length=len(q),
                    municipality="Prishtina",
                    section="api",
                ),
                request,
            )
        return result
    except TimeoutError as exc:
        log_api_abuse(
            reason="search_timeout",
            path=request.url.path,
            client_ip=request.client.host if request.client else None,
            timeout_sec=settings.api_search_timeout_sec,
        )
        raise HTTPException(status_code=504, detail="Search timed out") from exc


@app.get("/api/compare", response_model=CompareResponse)
def market_compare(
    session: DbSession,
    neighborhoods: str = Query(..., min_length=3, description="Comma-separated slugs, 2-3"),
) -> CompareResponse:
    slugs = [s.strip() for s in neighborhoods.split(",") if s.strip()]
    max_n = get_settings().api_compare_max_neighborhoods
    if len(slugs) > max_n:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {max_n} neighborhoods",
        )
    try:
        return compare_neighborhoods(session, slugs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/lookup/{entity_type}/{slug}/history", response_model=MarketHistory)
def market_history(
    session: DbSession,
    entity_type: EntityType,
    slug: str,
    months: int = Query(default=12, ge=6, le=12),
) -> MarketHistory:
    if entity_type not in ("neighborhood", "district", "street", "complex"):
        raise HTTPException(status_code=400, detail="Invalid entity type")
    result = get_market_history(session, entity_type, slug, months=months)
    if result is None:
        raise HTTPException(status_code=404, detail="Market segment not found")
    return result


@app.get("/api/lookup/{entity_type}/{slug}")
def market_lookup(
    response: Response, session: DbSession, entity_type: EntityType, slug: str
) -> dict:
    if entity_type not in ("neighborhood", "district", "street", "complex"):
        raise HTTPException(status_code=400, detail="Invalid entity type")
    result = resolve_market_lookup(session, entity_type, slug)
    if result is None:
        raise HTTPException(status_code=404, detail="Market segment not found")
    response.headers["Cache-Control"] = "public, max-age=60"
    response.headers["Vary"] = "Accept-Encoding"
    return result.model_dump()


@app.post("/api/budget-match", response_model=BudgetMatchResponse)
@limiter.limit(_rate_limit("api_rate_limit_events"))
def budget_match_api(
    request: Request,
    body: BudgetMatchRequest,
    session: DbSession,
) -> BudgetMatchResponse:
    result = budget_match(session, body)
    log_product_event(
        ProductEvent(
            event="budget_match",
            listing_type=body.listing_type,
            bedrooms=body.bedrooms,
            results_count=len(result.neighborhoods),
            success=bool(result.neighborhoods),
        ),
        request,
    )
    return result


@app.post("/api/valuate", response_model=ValuationResult)
@limiter.limit(_rate_limit("api_rate_limit_valuate"))
async def valuate(request: Request, body: ValuationRequest) -> ValuationResult:
    from groundtruth.analytics.valuation import comparables_cache_ready

    settings = get_settings()
    if not settings.is_development and not settings.valuation_public_enabled:
        raise HTTPException(
            status_code=503,
            detail="Valuation is unavailable while release validation is in progress.",
        )
    if not comparables_cache_ready():
        raise HTTPException(
            status_code=503,
            detail="Valuation data is still loading. Please try again shortly.",
        )

    had_asking = (
        body.listing_rent_eur is not None
        if body.valuation_type == "rent"
        else body.listing_sale_eur is not None
    )
    log_product_event(
        ProductEvent(
            event="valuation_requested",
            municipality="Prishtina",
            neighborhood=body.neighborhood,
            area_sqm=body.area_sqm,
            bedrooms=body.bedrooms,
            listing_type=body.valuation_type,
            valuation_type=body.valuation_type,
            property_type="apartment",
            had_asking=had_asking,
            had_listing_rent=had_asking,
        ),
        request,
    )

    def _run_valuation() -> ValuationResult:
        from groundtruth.analytics.valuation import (
            comparables_cache_ready,
            copy_cached_comparables_pair,
        )

        if comparables_cache_ready():
            pair = copy_cached_comparables_pair()
            if pair is not None:
                rent_df, sale_df = pair
                return estimate_valuation(
                    None,
                    body,
                    rent_comparables=rent_df,
                    sale_comparables=sale_df,
                )

        session = get_session_factory()()
        try:
            return estimate_valuation(session, body)
        finally:
            session.close()

    try:
        t0 = time.perf_counter()
        result = await asyncio.wait_for(
            asyncio.to_thread(_run_valuation),
            timeout=settings.api_valuate_timeout_sec,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        log_product_event(
            ProductEvent(
                event="valuation_completed",
                municipality="Prishtina",
                neighborhood=result.neighborhood_name,
                area_sqm=result.area_sqm,
                bedrooms=result.bedrooms,
                listing_type=body.valuation_type,
                valuation_type=body.valuation_type,
                property_type="apartment",
                had_asking=had_asking,
                had_listing_rent=had_asking,
                success=True,
                confidence_tier=result.confidence_label,
                confidence=result.confidence_label,
                response_time_ms=round(elapsed_ms, 1),
            ),
            request,
        )
        return result
    except TimeoutError as exc:
        log_api_abuse(
            reason="valuate_timeout",
            path=request.url.path,
            client_ip=request.client.host if request.client else None,
            timeout_sec=settings.api_valuate_timeout_sec,
        )
        raise HTTPException(
            status_code=504,
            detail="Valuation timed out. Try again or reduce filters.",
        ) from exc
    except ValueError as exc:
        log_product_event(
            ProductEvent(
                event="valuation_failed",
                municipality="Prishtina",
                neighborhood=body.neighborhood,
                area_sqm=body.area_sqm,
                bedrooms=body.bedrooms,
                listing_type=body.valuation_type,
                valuation_type=body.valuation_type,
                property_type="apartment",
                had_asking=had_asking,
                had_listing_rent=had_asking,
                success=False,
            ),
            request,
        )
        detail = INSUFFICIENT_EVIDENCE_MSG if str(exc) == INSUFFICIENT_EVIDENCE_MSG else str(exc)
        raise HTTPException(status_code=400, detail=detail) from exc
    except Exception as exc:
        from sqlalchemy.exc import SQLAlchemyError

        if isinstance(exc, SQLAlchemyError):
            logger.exception("valuate_database_error")
            raise HTTPException(
                status_code=503,
                detail="Database unavailable. Start Postgres: docker compose up -d postgres",
            ) from exc
        logger.exception("valuate_unhandled_error")
        raise HTTPException(status_code=500, detail="Valuation failed. Check server logs.") from exc


@app.post("/api/events")
@limiter.limit(_rate_limit("api_rate_limit_events"))
def track_event(request: Request, event: ProductEvent) -> dict[str, str]:
    log_product_event(event, request)
    return {"status": "ok"}


@app.post("/api/feedback")
@limiter.limit(_rate_limit("api_rate_limit_feedback"))
def submit_feedback(request: Request, feedback: DataFeedbackRequest) -> dict[str, str]:
    log_data_feedback(feedback)
    return {"status": "ok"}


@app.post("/api/alerts")
@limiter.limit(_rate_limit("api_rate_limit_alerts"))
def submit_alert(request: Request, alert: SavedAlertRequest) -> dict[str, str]:
    log_price_alert(alert)
    return {"status": "ok"}


@app.post("/api/contact")
@limiter.limit(_rate_limit("api_rate_limit_contact"))
def submit_contact(request: Request, contact: ContactRequest) -> dict[str, str]:
    append_product_submission("contact", contact.model_dump(exclude_none=True))
    return {"status": "ok"}


@app.post("/api/public-report")
@limiter.limit(_rate_limit("api_rate_limit_contact"))
def submit_public_report(request: Request, report: PublicReportRequest) -> dict[str, str]:
    append_product_submission("public_reports", report.model_dump(exclude_none=True))
    return {"status": "ok"}


@app.post("/api/listing-submissions")
@limiter.limit(_rate_limit("api_rate_limit_contact"))
def submit_listing_submission(
    request: Request,
    listing: ListingSubmissionRequest,
) -> dict[str, str]:
    append_product_submission("listing_submissions", listing.model_dump(exclude_none=True))
    return {"status": "ok"}


@app.post("/api/lang")
@limiter.limit(_rate_limit("api_rate_limit_lang"))
def set_language(request: Request, pref: LangPreference) -> JSONResponse:
    """Persist UI language in a session cookie (expires when browser closes)."""
    if pref.lang not in ("sq", "en"):
        raise HTTPException(status_code=400, detail="lang must be sq or en")
    response = JSONResponse({"lang": pref.lang})
    settings = get_settings()
    response.set_cookie(
        "metrik_lang",
        pref.lang,
        path="/",
        httponly=True,
        samesite="lax",
        secure=not settings.is_development,
    )
    return response


@app.get("/api/changelog", response_model=ChangelogResponse)
def public_changelog(
    category: ChangelogCategory | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
) -> ChangelogResponse:
    return load_public_changelog(category=category, limit=limit)


@app.get("/")
def index() -> HTMLResponse:
    return _html_page("index.html")


@app.get("/robots.txt")
def robots_txt() -> PlainTextResponse:
    return PlainTextResponse(
        "User-agent: *\nAllow: /\nSitemap: "
        f"{get_settings().public_base_url.rstrip('/')}/sitemap.xml\n"
    )


@app.get("/sitemap.xml")
def sitemap_xml() -> Response:
    from groundtruth.services.market_seo import market_sitemap_urls

    base = get_settings().public_base_url.rstrip("/")
    paths = [
        "/",
        "/valuate",
        "/find",
        "/statistics",
        "/compare",
        "/rent-yield",
        "/alerts",
        "/changelog",
        "/contact",
        "/methodology",
        "/privacy",
        "/terms",
    ]
    paths.extend(market_sitemap_urls())
    urls = "\n".join(f"  <url><loc>{base}{path}</loc></url>" for path in paths)
    xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>\n'
    return Response(content=xml, media_type="application/xml")


@app.get("/favicon.svg")
def favicon_svg() -> FileResponse:
    return FileResponse(WEB_DIR / "favicon.svg", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/favicon.ico")
def favicon_ico() -> FileResponse:
    return FileResponse(
        WEB_DIR / "favicon.svg",
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/valuate")
def valuate_page() -> HTMLResponse:
    return _html_page("valuate.html")


@app.get("/find")
def find_page() -> HTMLResponse:
    return _html_page("find.html")


@app.get("/statistics")
def statistics_page() -> HTMLResponse:
    return _html_page("statistics.html")


@app.get("/reports")
def reports_page() -> RedirectResponse:
    """Legacy URL — same content as /statistics."""
    return RedirectResponse("/statistics", status_code=308)


@app.get("/about")
def about_page() -> RedirectResponse:
    return RedirectResponse("/methodology", status_code=308)


@app.get("/methodology")
def methodology_page() -> HTMLResponse:
    return _html_page("methodology.html")


@app.get("/changelog")
def changelog_page() -> HTMLResponse:
    return _html_page("changelog.html")


@app.get("/alerts")
def alerts_page() -> HTMLResponse:
    return _html_page("alerts.html")


@app.get("/privacy")
def privacy_page() -> HTMLResponse:
    return _html_page("privacy.html")


@app.get("/terms")
def terms_page() -> HTMLResponse:
    return _html_page("terms.html")


@app.get("/annual")
def annual_page() -> RedirectResponse:
    """Legacy URL — same content as /statistics."""
    return RedirectResponse("/statistics", status_code=308)


@app.get("/compare")
def compare_page() -> HTMLResponse:
    return _html_page("compare.html")


@app.get("/rent-yield")
def rent_yield_page() -> HTMLResponse:
    return _html_page("rent-yield.html")


@app.get("/contact")
def contact_page() -> HTMLResponse:
    return _html_page("contact.html")


@app.get("/market/{entity_type}/{slug}")
def market_page(entity_type: EntityType, slug: str) -> HTMLResponse:
    if entity_type not in ("neighborhood", "district", "street", "complex"):
        raise HTTPException(status_code=404)
    from groundtruth.services.market_seo import render_market_html

    html = render_market_html(entity_type, slug, session=None)
    return HTMLResponse(content=html, headers={"Cache-Control": "no-cache"})


if WEB_DIR.exists():
    app.mount("/static", ProdStaticFiles(directory=WEB_DIR / "static"), name="static")
