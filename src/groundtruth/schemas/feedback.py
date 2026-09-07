"""Schemas for crowdsourced data-quality feedback."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

FeedbackKind = Literal["listing", "neighborhood"]
FeedbackIssue = Literal[
    "wrong_price",
    "wrong_location",
    "wrong_area",
    "duplicate",
    "outdated",
    "other",
]


class DataFeedbackRequest(BaseModel):
    kind: FeedbackKind
    issue: FeedbackIssue
    message: str | None = Field(default=None, max_length=500)
    source: str | None = None
    source_listing_id: str | None = None
    listing_url: str | None = Field(default=None, max_length=500)
    entity_type: str | None = None
    slug: str | None = None
    display_name: str | None = Field(default=None, max_length=200)
    page_url: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_context(self) -> DataFeedbackRequest:
        if self.kind == "listing":
            if not self.source or not self.source_listing_id:
                raise ValueError("Listing feedback requires source and source_listing_id")
        elif self.kind == "neighborhood" and (not self.entity_type or not self.slug):
            raise ValueError("Neighborhood feedback requires entity_type and slug")
        if self.issue == "other" and not (self.message and self.message.strip()):
            raise ValueError("Please describe the issue when selecting Other")
        return self
