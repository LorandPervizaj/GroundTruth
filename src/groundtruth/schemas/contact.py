"""Schemas for public contact, report, and listing submission forms."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ContactRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=5, max_length=200)
    topic: Literal["general", "data", "partnership", "press", "other"] = "general"
    message: str = Field(min_length=10, max_length=2000)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        email = value.strip().lower()
        if "@" not in email:
            raise ValueError("Valid email required")
        return email


class PublicReportRequest(BaseModel):
    issue: Literal[
        "wrong_price",
        "wrong_location",
        "wrong_area",
        "duplicate",
        "outdated",
        "missing_market",
        "bug",
        "other",
    ]
    page_url: str | None = Field(default=None, max_length=500)
    listing_url: str | None = Field(default=None, max_length=500)
    email: str | None = Field(default=None, max_length=200)
    message: str = Field(min_length=10, max_length=2000)

    @field_validator("email")
    @classmethod
    def validate_optional_email(cls, value: str | None) -> str | None:
        if value is None or value.strip() == "":
            return None
        email = value.strip().lower()
        if "@" not in email:
            raise ValueError("Valid email required")
        return email


class ListingSubmissionRequest(BaseModel):
    submitter_email: str | None = Field(default=None, max_length=200)
    listing_url: str | None = Field(default=None, max_length=500)
    source: str | None = Field(default=None, max_length=80)
    listing_type: Literal["rent", "sale"]
    property_type: Literal["apartment", "house", "land", "commercial", "other"] = "apartment"
    city: str = Field(default="Prishtina", max_length=100)
    neighborhood: str | None = Field(default=None, max_length=120)
    street: str | None = Field(default=None, max_length=160)
    price_eur: int | None = Field(default=None, ge=1, le=10_000_000)
    area_sqm: float | None = Field(default=None, gt=0, le=5000)
    bedrooms: int | None = Field(default=None, ge=0, le=20)
    notes: str | None = Field(default=None, max_length=1500)

    @field_validator("submitter_email")
    @classmethod
    def validate_optional_email(cls, value: str | None) -> str | None:
        if value is None or value.strip() == "":
            return None
        email = value.strip().lower()
        if "@" not in email:
            raise ValueError("Valid email required")
        return email

    @model_validator(mode="after")
    def validate_listing_context(self) -> ListingSubmissionRequest:
        if not self.listing_url and not self.notes:
            raise ValueError("Provide a listing URL or enough details in notes")
        return self
