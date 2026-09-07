"""SQLAlchemy engine and session factory."""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from groundtruth.config import Settings, get_settings


@lru_cache
def get_engine(settings: Settings | None = None) -> Engine:
    """Create and cache the SQLAlchemy engine."""
    settings = settings or get_settings()
    return create_engine(
        str(settings.database_url),
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        echo=settings.is_development and False,
        connect_args={"connect_timeout": 5},
    )


@lru_cache
def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    """Return a configured session factory."""
    return sessionmaker(bind=get_engine(settings), autoflush=False, autocommit=False)


def get_session() -> Generator[Session, None, None]:
    """Yield a database session for dependency injection."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# FastAPI Depends alias
get_db = get_session
