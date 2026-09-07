"""Domain enumerations."""

import enum


class ListingType(enum.StrEnum):
    SALE = "sale"
    RENT = "rent"


class PropertyType(enum.StrEnum):
    APARTMENT = "apartment"
    HOUSE = "house"
    STUDIO = "studio"
    ROOM = "room"
    VILLA = "villa"
    LAND = "land"
    COMMERCIAL = "commercial"
    GARAGE = "garage"
    OTHER = "other"


class Currency(enum.StrEnum):
    EUR = "EUR"
    USD = "USD"
    CHF = "CHF"
    UNKNOWN = "UNKNOWN"


class HeatingType(enum.StrEnum):
    CENTRAL = "central"
    GAS = "gas"
    ELECTRIC = "electric"
    WOOD = "wood"
    NONE = "none"
    OTHER = "other"
    UNKNOWN = "unknown"


class BuildingAgeCategory(enum.StrEnum):
    NEW = "new"
    MODERN = "modern"
    OLD = "old"
    UNKNOWN = "unknown"


class PipelineStage(enum.StrEnum):
    PARSE = "parse"
    NORMALIZE = "normalize"
    VALIDATE = "validate"


class ScrapeRunStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PropertyEventType(enum.StrEnum):
    """Lifecycle events for a canonical property."""

    LISTED = "listed"
    PRICE_REDUCED = "price_reduced"
    PRICE_INCREASED = "price_increased"
    RELISTED = "relisted"
    SOLD = "sold"
    REMOVED = "removed"
    STATUS_CHANGED = "status_changed"
