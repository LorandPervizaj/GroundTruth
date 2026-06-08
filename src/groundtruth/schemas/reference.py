"""Pydantic schemas for gazetteer reference entities."""

from pydantic import BaseModel, ConfigDict, Field


class NeighborhoodSchema(BaseModel):
    """Neighborhood gazetteer entry."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    slug: str
    city: str
    centroid_lat: float | None = None
    centroid_lng: float | None = None
    aliases: list[str] = Field(default_factory=list)


class StreetSchema(BaseModel):
    """Street gazetteer entry."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    slug: str
    neighborhood_slug: str | None = None
    aliases: list[str] = Field(default_factory=list)


class ComplexSchema(BaseModel):
    """Residential complex gazetteer entry."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    slug: str
    neighborhood_slug: str | None = None
    aliases: list[str] = Field(default_factory=list)
    notes: str | None = None


class BuildingSchema(BaseModel):
    """Building alias gazetteer entry."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    slug: str
    complex_slug: str | None = None
    neighborhood_slug: str | None = None
    aliases: list[str] = Field(default_factory=list)
