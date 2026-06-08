"""Domain enumerations."""

import enum


class ListingType(str, enum.Enum):
    SALE = "sale"
    RENT = "rent"


class PropertyType(str, enum.Enum):
    APARTMENT = "apartment"
    HOUSE = "house"
    STUDIO = "studio"
    ROOM = "room"
    VILLA = "villa"
    LAND = "land"
    COMMERCIAL = "commercial"
    GARAGE = "garage"
    OTHER = "other"


class Currency(str, enum.Enum):
    EUR = "EUR"
    USD = "USD"
    CHF = "CHF"
    UNKNOWN = "UNKNOWN"


class HeatingType(str, enum.Enum):
    CENTRAL = "central"
    GAS = "gas"
    ELECTRIC = "electric"
    WOOD = "wood"
    NONE = "none"
    OTHER = "other"
    UNKNOWN = "unknown"


class BuildingAgeCategory(str, enum.Enum):
    NEW = "new"
    MODERN = "modern"
    OLD = "old"
    UNKNOWN = "unknown"


class PipelineStage(str, enum.Enum):
    PARSE = "parse"
    NORMALIZE = "normalize"
    VALIDATE = "validate"


class ScrapeRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PropertyEventType(str, enum.Enum):
    """Lifecycle events for a canonical property."""

    LISTED = "listed"
    PRICE_REDUCED = "price_reduced"
    PRICE_INCREASED = "price_increased"
    RELISTED = "relisted"
    SOLD = "sold"
    REMOVED = "removed"
    STATUS_CHANGED = "status_changed"
