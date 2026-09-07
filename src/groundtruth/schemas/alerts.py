"""Schemas for saved neighborhood price alerts (v1 — signup only)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

AlertListingType = Literal["sale", "rent", "both"]


class SavedAlertRequest(BaseModel):
    email: str = Field(max_length=200)
    neighborhood_slug: str = Field(min_length=2, max_length=80)
    listing_type: AlertListingType = "both"
    max_price_eur: int | None = Field(default=None, ge=50, le=5_000_000)
    min_price_eur: int | None = Field(default=None, ge=50, le=5_000_000)
    note: str | None = Field(default=None, max_length=300)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        email = value.strip().lower()
        if "@" not in email or len(email) < 5:
            raise ValueError("Valid email required")
        return email
