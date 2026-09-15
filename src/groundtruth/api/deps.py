"""Shared FastAPI dependencies and small route helpers.

Kept outside ``app`` so route modules never import the application object.
"""

from __future__ import annotations

import secrets
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from groundtruth.config import get_settings
from groundtruth.database.session import get_session

EntityType = Literal["neighborhood", "district", "street", "complex"]
DbSession = Annotated[Session, Depends(get_session)]


def require_ops_access(request: Request) -> None:
    """Hide operational endpoints unless the configured token matches."""
    settings = get_settings()
    if settings.is_development:
        return
    expected = settings.health_check_token
    provided = request.headers.get("X-Health-Token")
    if not expected or not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=404, detail="Not found")


def rate_limit(limit_key: str):
    """Resolve per-route limit string from settings at request time."""
    return lambda: getattr(get_settings(), limit_key)


def set_public_cache(response: Response, *, max_age: int = 60) -> None:
    """Allow short browser/CDN caching for stable aggregate GET payloads."""
    response.headers["Cache-Control"] = f"public, max-age={max_age}"
    response.headers["Vary"] = "Accept-Encoding"
