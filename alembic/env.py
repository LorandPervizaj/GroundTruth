"""Alembic migration environment."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from groundtruth.config import get_settings
from groundtruth.models import Base  # noqa: F401 — registers all models
from groundtruth.models.canonical import CanonicalProperty, ListingSource, PriceHistory  # noqa: F401
from groundtruth.models.etl import EtlMetrics, InvalidListing  # noqa: F401
from groundtruth.models.events import PropertyEvent  # noqa: F401
from groundtruth.models.market import MarketSnapshot  # noqa: F401
from groundtruth.models.pipeline import NormalizedListing, ParsedListing, RawListing  # noqa: F401
from groundtruth.models.reference import Building, Complex, Neighborhood, Street  # noqa: F401
from groundtruth.models.scrape_run import ScrapeRun  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

settings = get_settings()
config.set_main_option("sqlalchemy.url", str(settings.database_url))


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
