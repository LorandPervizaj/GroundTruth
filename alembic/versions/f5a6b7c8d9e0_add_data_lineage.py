"""add data_lineage table

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-06-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f5a6b7c8d9e0"
down_revision: str | None = "e4f5a6b7c8d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_lineage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("normalized_listing_id", sa.Integer(), nullable=False),
        sa.Column("raw_listing_id", sa.Integer(), nullable=False),
        sa.Column("parsed_listing_id", sa.Integer(), nullable=False),
        sa.Column("etl_metrics_id", sa.Integer(), nullable=True),
        sa.Column("parser_version", sa.String(length=20), nullable=False),
        sa.Column("normalization_version", sa.String(length=20), nullable=False),
        sa.Column("gazetteer_version", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["etl_metrics_id"], ["etl_metrics.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["normalized_listing_id"], ["normalized_listings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parsed_listing_id"], ["parsed_listings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["raw_listing_id"], ["raw_listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_data_lineage_etl_metrics_id"),
        "data_lineage",
        ["etl_metrics_id"],
    )
    op.create_index(
        op.f("ix_data_lineage_normalized_listing_id"),
        "data_lineage",
        ["normalized_listing_id"],
    )
    op.create_index(
        op.f("ix_data_lineage_raw_listing_id"),
        "data_lineage",
        ["raw_listing_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_data_lineage_raw_listing_id"), table_name="data_lineage")
    op.drop_index(op.f("ix_data_lineage_normalized_listing_id"), table_name="data_lineage")
    op.drop_index(op.f("ix_data_lineage_etl_metrics_id"), table_name="data_lineage")
    op.drop_table("data_lineage")
