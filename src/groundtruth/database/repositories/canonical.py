"""Repository for canonical properties and provenance."""

from sqlalchemy.orm import Session

from groundtruth.database.repositories.base import BaseRepository
from groundtruth.models.canonical import CanonicalProperty, ListingSource
from groundtruth.schemas.canonical import CanonicalPropertySchema, ListingSourceSchema


class CanonicalPropertyRepository(BaseRepository[CanonicalProperty]):
    """Persistence for deduplicated canonical properties."""

    model = CanonicalProperty

    def __init__(self, session: Session) -> None:
        super().__init__(session)

    def create_from_schema(self, schema: CanonicalPropertySchema) -> CanonicalProperty:
        """Create a canonical property from schema."""
        data = schema.model_dump(exclude={"id"}, exclude_none=True)
        entity = CanonicalProperty(**data)
        return self.add(entity)

    def link_source(
        self,
        canonical: CanonicalProperty,
        schema: ListingSourceSchema,
    ) -> ListingSource:
        """Link a source listing to a canonical property."""
        source = ListingSource(
            canonical_property_id=canonical.id,
            normalized_listing_id=schema.normalized_listing_id,
            parsed_listing_id=schema.parsed_listing_id,
            source_website=schema.source_website,
            source_listing_id=schema.source_listing_id,
            original_url=schema.original_url,
            is_primary_source=schema.is_primary_source,
            duplicate_confidence=schema.duplicate_confidence,
            duplicate_match_fields=schema.duplicate_match_fields or None,
        )
        self._session.add(source)
        self._session.flush()
        return source
