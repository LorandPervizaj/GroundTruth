"""Public changelog / transparency feed."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

ChangelogCategory = Literal["source", "parser", "methodology", "product", "data_quality"]


class ChangelogEntry(BaseModel):
    date: date
    category: ChangelogCategory
    title_sq: str
    title_en: str
    body_sq: str
    body_en: str
    component: str | None = None
    version: str | None = None


class ChangelogResponse(BaseModel):
    entries: list[ChangelogEntry] = Field(default_factory=list)
