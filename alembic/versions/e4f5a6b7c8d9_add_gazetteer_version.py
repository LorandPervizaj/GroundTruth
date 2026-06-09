"""add gazetteer_version to normalized_listings and etl_metrics

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-06-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: str | None = "d3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "normalized_listings",
        sa.Column("gazetteer_version", sa.String(length=20), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "etl_metrics",
        sa.Column("gazetteer_version", sa.String(length=20), nullable=False, server_default="unknown"),
    )


def downgrade() -> None:
    op.drop_column("etl_metrics", "gazetteer_version")
    op.drop_column("normalized_listings", "gazetteer_version")
