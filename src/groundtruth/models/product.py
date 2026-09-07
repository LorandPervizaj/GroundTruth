"""Durable product interaction submissions for public Metrik forms/events."""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from groundtruth.models.base import Base, TimestampMixin


class ProductSubmission(Base, TimestampMixin):
    """Append-only product submission/event payload.

    Payloads are schema-validated before insertion by the public API services.
    Storing JSONB keeps the v1 product surface flexible while avoiding local
    JSONL files on production hosts.
    """

    __tablename__ = "product_submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
