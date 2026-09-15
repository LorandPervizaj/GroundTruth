"""Public market / product read (and valuation) API routes."""

from __future__ import annotations

import asyncio
import logging
import secrets
import time

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from groundtruth.analytics.valuation import (
    INSUFFICIENT_EVIDENCE_MSG,
    compute_public_valuation,
    list_neighborhood_options,
)
from groundtruth.api.deps import DbSession, EntityType, rate_limit, set_public_cache
from groundtruth.api.security import limiter, log_api_abuse
from groundtruth.config import get_settings
from groundtruth.database.session import get_session_factory
from groundtruth.schemas.budget_match import BudgetMatchRequest, BudgetMatchResponse
from groundtruth.schemas.lookup import (
    CompareResponse,
    CorpusMeta,
    MarketHistory,
    MarketLookup,
    NeighborhoodMarketSummary,
    SearchResponse,
)
from groundtruth.schemas.methodology import MethodologyPublic
from groundtruth.schemas.product_analytics import ProductEvent
from groundtruth.schemas.rent_yield import RentYieldResponse
from groundtruth.schemas.valuation import (
    NeighborhoodOption,
    ValuationRequest,
    ValuationResult,
)
from groundtruth.services.budget_match import budget_match
from groundtruth.services.lookup import (
    compare_neighborhoods,
    get_corpus_meta,
    get_market_history,
    list_neighborhood_market_summaries,
)
from groundtruth.services.lookup_cache import (
    corpus_meta_from_cache,
    resolve_market_lookup,
)
from groundtruth.services.methodology_public import get_public_methodology
from groundtruth.services.product_analytics import log_product_event
from groundtruth.services.readiness import evaluate_readiness
from groundtruth.services.rent_yield import (
    build_rent_yield_from_lookup_cache,
    build_rent_yield_table,
    load_rent_yield_cache,
)
from groundtruth.services.search import run_public_search

router = APIRouter(tags=["markets"])
logger = logging.getLogger(__name__)


@router.get("/api/neighborhoods", response_model=list[NeighborhoodOption])
def neighborhoods(response: Response, session: DbSession) -> list[NeighborhoodOption]:
    from groundtruth.services.lookup_cache import cache_is_loaded, get_cached_neighborhood_options

    set_public_cache(response, max_age=120)
    if cache_is_loaded():
        rows = get_cached_neighborhood_options()
        if rows:
            return [NeighborhoodOption.model_validate(row) for row in rows]
    rows = list_neighborhood_options(session)
    return [NeighborhoodOption.model_validate(row) for row in rows]


@router.get("/api/methodology", response_model=MethodologyPublic)
def methodology_meta(session: DbSession) -> MethodologyPublic:
    return get_public_methodology(session)


@router.get("/api/meta", response_model=CorpusMeta)
def corpus_meta(response: Response, session: DbSession) -> CorpusMeta:
    set_public_cache(response, max_age=60)
    cached = corpus_meta_from_cache(session)
    if cached is not None:
        return cached
    return get_corpus_meta(session)


@router.get("/api/ready")
def api_ready(request: Request) -> JSONResponse:
    """Readiness probe — HTTP 200 when ready, HTTP 503 when not.

    Body always includes machine-readable ``ok`` and, on failure, ``reasons``.
    """
    from groundtruth.analytics.valuation import comparables_cache_ready
    from groundtruth.services.artifact_integrity import get_artifact_integrity_state
    from groundtruth.services.lookup_cache import cache_is_loaded

    settings = get_settings()
    payload = evaluate_readiness(settings)
    lookup_cache = cache_is_loaded()
    comparables_ready = comparables_cache_ready()
    integrity = get_artifact_integrity_state()

    detail = {
        "environment": settings.app_env,
        "lookup_cache": lookup_cache,
        "comparables_ready": comparables_ready,
        "artifacts_verified": integrity.verified,
    }
    if integrity.error:
        detail["artifact_error"] = integrity.error

    if settings.is_development:
        payload.update(detail)
    else:
        expected = settings.health_check_token
        provided = request.headers.get("X-Health-Token")
        if expected and provided and secrets.compare_digest(provided, expected):
            payload.update(detail)

    status = 200 if payload.get("ok") else 503
    if status == 503:
        logging.getLogger(__name__).warning("readiness_failed reasons=%s", payload.get("reasons"))
    return JSONResponse(content=payload, status_code=status)


@router.get("/api/markets", response_model=list[NeighborhoodMarketSummary])
def markets(response: Response, session: DbSession) -> list[NeighborhoodMarketSummary]:
    from groundtruth.services.lookup_cache import cache_is_loaded, get_cached_markets

    set_public_cache(response, max_age=120)
    if cache_is_loaded():
        return get_cached_markets()
    return list_neighborhood_market_summaries(session)


@router.get("/api/rent-yield", response_model=RentYieldResponse)
def rent_yield(response: Response) -> RentYieldResponse:
    """Neighborhood gross rent yield where rent and sale samples are sufficient."""
    from groundtruth.services.lookup_cache import cache_is_loaded

    set_public_cache(response, max_age=120)
    if cache_is_loaded():
        rows = build_rent_yield_from_lookup_cache()
        if rows:
            return RentYieldResponse(rows=rows, cached=True)

    cached = load_rent_yield_cache()
    if cached:
        return RentYieldResponse(rows=cached, cached=True)

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
        return RentYieldResponse(rows=rows)
    return RentYieldResponse(rows=[])


@router.get("/api/search", response_model=SearchResponse)
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

    try:
        t0 = time.perf_counter()
        result = await asyncio.wait_for(
            asyncio.to_thread(run_public_search, q),
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


@router.get("/api/compare", response_model=CompareResponse)
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


@router.get("/api/lookup/{entity_type}/{slug}/history", response_model=MarketHistory)
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


@router.get("/api/lookup/{entity_type}/{slug}", response_model=MarketLookup)
def market_lookup(
    response: Response, session: DbSession, entity_type: EntityType, slug: str
) -> MarketLookup:
    if entity_type not in ("neighborhood", "district", "street", "complex"):
        raise HTTPException(status_code=400, detail="Invalid entity type")
    result = resolve_market_lookup(session, entity_type, slug)
    if result is None:
        raise HTTPException(status_code=404, detail="Market segment not found")
    response.headers["Cache-Control"] = "public, max-age=60"
    response.headers["Vary"] = "Accept-Encoding"
    return result


@router.post("/api/budget-match", response_model=BudgetMatchResponse)
@limiter.limit(rate_limit("api_rate_limit_events"))
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


@router.post("/api/valuate", response_model=ValuationResult)
@limiter.limit(rate_limit("api_rate_limit_valuate"))
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

    try:
        t0 = time.perf_counter()
        result = await asyncio.wait_for(
            asyncio.to_thread(compute_public_valuation, body),
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
