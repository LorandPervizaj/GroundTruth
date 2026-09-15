"""add composite index for active corpus DISTINCT ON hot path

Revision ID: g1h2i3j4k5l6
Revises: c8d9e0f1a2b3
Create Date: 2026-09-08
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "g1h2i3j4k5l6"
down_revision: str | Sequence[str] | None = "c8d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Matches DISTINCT ON (source_website, source_listing_id) … ORDER BY … id DESC
    # plus common active-corpus filters on parser_version / listing_date.
    op.create_index(
        "ix_normalized_listings_corpus_hot",
        "normalized_listings",
        ["source_website", "source_listing_id", "id"],
        unique=False,
        postgresql_ops={"id": "DESC"},
    )
    op.create_index(
        "ix_normalized_listings_parser_listing_date",
        "normalized_listings",
        ["parser_version", "listing_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_normalized_listings_parser_listing_date",
        table_name="normalized_listings",
    )
    op.drop_index(
        "ix_normalized_listings_corpus_hot",
        table_name="normalized_listings",
    )
