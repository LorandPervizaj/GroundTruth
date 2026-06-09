"""add listing_observations table

Revision ID: a1b2c3d4e5f6
Revises: f5a6b7c8d9e0
Create Date: 2026-06-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f5a6b7c8d9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "listing_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_website", sa.String(length=100), nullable=False),
        sa.Column("source_listing_id", sa.String(length=255), nullable=False),
        sa.Column("normalized_listing_id", sa.Integer(), nullable=True),
        sa.Column("observed_date", sa.Date(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("listing_type", sa.String(length=20), nullable=True),
        sa.Column("sale_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("rent_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("area_sqm", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("parser_version", sa.String(length=20), nullable=True),
        sa.Column("original_url", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["normalized_listing_id"], ["normalized_listings.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_website",
            "source_listing_id",
            "observed_date",
            name="uq_listing_observation_day",
        ),
    )
    op.create_index("ix_listing_observations_source_website", "listing_observations", ["source_website"])
    op.create_index("ix_listing_observations_source_listing_id", "listing_observations", ["source_listing_id"])
    op.create_index("ix_listing_observations_observed_date", "listing_observations", ["observed_date"])


def downgrade() -> None:
    op.drop_table("listing_observations")
