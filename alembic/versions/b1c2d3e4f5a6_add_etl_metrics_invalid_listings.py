"""add etl_metrics and invalid_listings tables

Revision ID: b1c2d3e4f5a6
Revises: adb5dffa0529
Create Date: 2026-06-08 10:45:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "adb5dffa0529"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "etl_metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scrape_run_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("parser_version", sa.String(length=20), nullable=False),
        sa.Column("normalization_version", sa.String(length=20), nullable=False),
        sa.Column("total_scraped", sa.Integer(), nullable=False),
        sa.Column("parsed_success", sa.Integer(), nullable=False),
        sa.Column("parsed_failed", sa.Integer(), nullable=False),
        sa.Column("normalized_success", sa.Integer(), nullable=False),
        sa.Column("normalized_failed", sa.Integer(), nullable=False),
        sa.Column("validation_failed", sa.Integer(), nullable=False),
        sa.Column("duplicate_candidates", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("field_rates", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["scrape_run_id"], ["scrape_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_etl_metrics_scrape_run_id"), "etl_metrics", ["scrape_run_id"])
    op.create_index(op.f("ix_etl_metrics_source"), "etl_metrics", ["source"])

    op.create_table(
        "invalid_listings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scrape_run_id", sa.Integer(), nullable=True),
        sa.Column("raw_listing_id", sa.Integer(), nullable=True),
        sa.Column("parsed_listing_id", sa.Integer(), nullable=True),
        sa.Column("normalized_listing_id", sa.Integer(), nullable=True),
        sa.Column(
            "stage",
            sa.Enum("parse", "normalize", "validate", name="pipeline_stage", native_enum=False),
            nullable=False,
        ),
        sa.Column("error_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("field_errors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["normalized_listing_id"], ["normalized_listings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parsed_listing_id"], ["parsed_listings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["raw_listing_id"], ["raw_listings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["scrape_run_id"], ["scrape_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_invalid_listings_scrape_run_id"), "invalid_listings", ["scrape_run_id"])
    op.create_index(op.f("ix_invalid_listings_raw_listing_id"), "invalid_listings", ["raw_listing_id"])
    op.create_index(op.f("ix_invalid_listings_parsed_listing_id"), "invalid_listings", ["parsed_listing_id"])
    op.create_index(
        op.f("ix_invalid_listings_normalized_listing_id"),
        "invalid_listings",
        ["normalized_listing_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_invalid_listings_normalized_listing_id"), table_name="invalid_listings")
    op.drop_index(op.f("ix_invalid_listings_parsed_listing_id"), table_name="invalid_listings")
    op.drop_index(op.f("ix_invalid_listings_raw_listing_id"), table_name="invalid_listings")
    op.drop_index(op.f("ix_invalid_listings_scrape_run_id"), table_name="invalid_listings")
    op.drop_table("invalid_listings")
    op.drop_index(op.f("ix_etl_metrics_source"), table_name="etl_metrics")
    op.drop_index(op.f("ix_etl_metrics_scrape_run_id"), table_name="etl_metrics")
    op.drop_table("etl_metrics")
