"""add parser_version and scraped_at to pipeline tables

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-08 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "parsed_listings",
        sa.Column("parser_version", sa.String(length=20), nullable=False, server_default="1.0.0"),
    )
    op.add_column(
        "normalized_listings",
        sa.Column("parser_version", sa.String(length=20), nullable=False, server_default="1.0.0"),
    )
    op.add_column(
        "normalized_listings",
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("normalized_listings", "scraped_at")
    op.drop_column("normalized_listings", "parser_version")
    op.drop_column("parsed_listings", "parser_version")
