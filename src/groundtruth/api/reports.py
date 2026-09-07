"""Serve published static market reports from reports/generated."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from groundtruth.analytics.annual_export import (
    corpus_data_revision,
    export_annual_report,
    finalize_annual_report_payload,
    load_annual_report_cache,
)
from groundtruth.analytics.annual_report import build_annual_report_payload
from groundtruth.api.security import limiter
from groundtruth.config import PROJECT_ROOT, get_settings
from groundtruth.database.session import get_session, get_session_factory
from groundtruth.schemas.product_analytics import ProductEvent
from groundtruth.services.product_analytics import log_product_event

router = APIRouter(prefix="/api/reports", tags=["reports"])

REPORT_CATALOG: list[dict[str, str]] = [
    {
        "pattern": "quarterly_report_*.md",
        "type": "Quarterly",
        "title": "Quarterly market report",
        "description": "Neighborhood-level rent and sale overview for Prishtina.",
        "teaser": "Quarterly overview of neighborhood rents and sale prices.",
        "featured": "true",
    },
    {
        "pattern": "corpus_report_*.md",
        "type": "Corpus",
        "title": "Corpus report",
        "description": "Data quality, coverage, and missingness across the listing database.",
        "teaser": "Corpus health and coverage across sources.",
        "featured": "false",
    },
    {
        "pattern": "coverage_*.md",
        "type": "Coverage",
        "title": "Coverage report",
        "description": "Where rent and sale comparables are thin vs ready for estimates.",
        "teaser": "Which neighborhoods have enough data for reliable estimates.",
        "featured": "false",
    },
    {
        "pattern": "market_report_*.md",
        "type": "Market",
        "title": "Market report",
        "description": "Snapshot of neighborhood market statistics.",
        "teaser": "Neighborhood market snapshot.",
        "featured": "false",
    },
]


class ReportItem(BaseModel):
    title: str
    type: str
    description: str
    teaser: str
    date: str
    filename: str
    url: str
    featured: bool = False


class ReportListResponse(BaseModel):
    reports: list[ReportItem]


def _reports_dir() -> Path:
    base = get_settings().reports_generated_dir
    if not base.is_absolute():
        base = PROJECT_ROOT / base
    return base


def _discover_reports() -> list[ReportItem]:
    out: list[ReportItem] = []
    root = _reports_dir()
    if not root.exists():
        return out

    for spec in REPORT_CATALOG:
        matches = sorted(root.glob(spec["pattern"]), key=lambda p: p.stat().st_mtime, reverse=True)
        if not matches:
            continue
        path = matches[0]
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        out.append(
            ReportItem(
                title=f"{spec['title']} ({mtime.strftime('%Y-%m-%d')})",
                type=spec["type"],
                description=spec["description"],
                teaser=spec["teaser"],
                date=mtime.isoformat(),
                filename=path.name,
                url=f"/api/reports/files/{path.name}",
                featured=spec.get("featured") == "true",
            )
        )

    out.sort(key=lambda r: r.date, reverse=True)
    if out and not any(r.featured for r in out):
        out[0].featured = True
    return out


_SAFE_FILENAME = re.compile(r"^[a-zA-Z0-9_][\w.-]*\.md$")


@router.get("", response_model=ReportListResponse)
def list_reports() -> ReportListResponse:
    return ReportListResponse(reports=_discover_reports())


@router.get("/files/{filename}")
def get_report_file(filename: str):
    if not _SAFE_FILENAME.match(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = _reports_dir() / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Report not found")
    return PlainTextResponse(
        path.read_text(encoding="utf-8"),
        media_type="text/markdown; charset=utf-8",
    )


def _annual_data_payload(*, force_refresh: bool = False) -> dict:
    """Serve cached statistics JSON; rebuild only when missing or explicitly refreshed."""
    cached = load_annual_report_cache()
    if not force_refresh and cached is not None:
        return cached

    session = get_session_factory()()
    try:
        revision = corpus_data_revision(session)
        export_annual_report(session)
        refreshed = load_annual_report_cache()
        if refreshed is not None:
            return refreshed
        return finalize_annual_report_payload(
            build_annual_report_payload(session),
            data_revision=revision,
        )
    finally:
        session.close()


def _report_refresh_limit() -> str:
    return get_settings().api_rate_limit_report_refresh


@router.get("/annual_data")
def get_annual_data(refresh: bool = Query(False)):
    # ?refresh=true bypasses cache but is dev-only; production uses ETL-scheduled export.
    if refresh:
        if not get_settings().is_development:
            raise HTTPException(
                status_code=403,
                detail="Cache refresh not available via query param",
            )
        return _annual_data_payload(force_refresh=True)
    return _annual_data_payload()


@router.post("/annual_data/refresh")
@limiter.limit(_report_refresh_limit)
def refresh_annual_data(request: Request, session: Session = Depends(get_session)):
    """Rebuild the cached annual report JSON (same artifact ETL writes). Dev-only."""
    if not get_settings().is_development:
        raise HTTPException(status_code=403, detail="Not available")
    path = export_annual_report(session)
    return {"ok": True, "path": str(path)}


@router.get("/annual_pdf")
def get_annual_pdf(request: Request, lang: str = Query("sq")):
    """Download NYSAR-style annual market report PDF."""
    if lang not in ("sq", "en"):
        raise HTTPException(status_code=400, detail="lang must be sq or en")
    log_product_event(
        ProductEvent(
            event="report_downloaded",
            report_type="annual_pdf",
            municipality="Prishtina",
            section=lang,
        ),
        request,
    )
    try:
        from groundtruth.analytics.annual_pdf import build_annual_pdf_bytes
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="PDF export unavailable. Install reportlab (uv sync).",
        ) from exc
    data = _annual_data_payload()
    try:
        pdf = build_annual_pdf_bytes(data, lang=lang)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    year = data.get("generated_at", "")[:4] or "annual"
    filename = f"metrik_prishtina_annual_{year}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
