"""Base repository with common CRUD operations."""

from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from groundtruth.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository[ModelT: Base]:
    """Generic repository implementing basic persistence operations."""

    model: type[ModelT]

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, entity_id: int) -> ModelT | None:
        """Fetch a single entity by primary key."""
        return self._session.get(self.model, entity_id)

    def add(self, entity: ModelT) -> ModelT:
        """Add an entity to the session."""
        self._session.add(entity)
        self._session.flush()
        return entity

    def add_all(self, entities: list[ModelT]) -> list[ModelT]:
        """Add multiple entities to the session."""
        self._session.add_all(entities)
        self._session.flush()
        return entities

    def delete(self, entity: ModelT) -> None:
        """Delete an entity from the session."""
        self._session.delete(entity)

    def list_all(self, limit: int = 100, offset: int = 0) -> list[ModelT]:
        """List entities with pagination."""
        stmt = select(self.model).limit(limit).offset(offset)
        return list(self._session.scalars(stmt).all())
