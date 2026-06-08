"""add confidence_score to normalized_listings

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-06-08 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d3e4f5a6b7c8"
down_revision: str | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("normalized_listings", sa.Column("confidence_score", sa.Float(), nullable=True))
    op.add_column(
        "normalized_listings",
        sa.Column("confidence_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        op.f("ix_normalized_listings_confidence_score"),
        "normalized_listings",
        ["confidence_score"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_normalized_listings_confidence_score"), table_name="normalized_listings")
    op.drop_column("normalized_listings", "confidence_details")
    op.drop_column("normalized_listings", "confidence_score")
