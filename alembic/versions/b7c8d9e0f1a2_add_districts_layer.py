"""add districts layer

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-06-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "districts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("neighborhood_id", sa.Integer(), nullable=False),
        sa.Column("aliases", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("district_type", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["neighborhood_id"], ["neighborhoods.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("neighborhood_id", "slug", name="uq_district_neighborhood_slug"),
    )
    op.create_index(op.f("ix_districts_neighborhood_id"), "districts", ["neighborhood_id"], unique=False)
    op.create_index(op.f("ix_districts_slug"), "districts", ["slug"], unique=False)

    op.add_column("complexes", sa.Column("district_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_complexes_district_id", "complexes", "districts", ["district_id"], ["id"], ondelete="SET NULL")
    op.create_index(op.f("ix_complexes_district_id"), "complexes", ["district_id"], unique=False)

    op.add_column("parsed_listings", sa.Column("district_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_parsed_listings_district_id", "parsed_listings", "districts", ["district_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index(op.f("ix_parsed_listings_district_id"), "parsed_listings", ["district_id"], unique=False)

    op.add_column("normalized_listings", sa.Column("district_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_normalized_listings_district_id",
        "normalized_listings",
        "districts",
        ["district_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_normalized_listings_district_id"), "normalized_listings", ["district_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_normalized_listings_district_id"), table_name="normalized_listings")
    op.drop_constraint("fk_normalized_listings_district_id", "normalized_listings", type_="foreignkey")
    op.drop_column("normalized_listings", "district_id")

    op.drop_index(op.f("ix_parsed_listings_district_id"), table_name="parsed_listings")
    op.drop_constraint("fk_parsed_listings_district_id", "parsed_listings", type_="foreignkey")
    op.drop_column("parsed_listings", "district_id")

    op.drop_index(op.f("ix_complexes_district_id"), table_name="complexes")
    op.drop_constraint("fk_complexes_district_id", "complexes", type_="foreignkey")
    op.drop_column("complexes", "district_id")

    op.drop_index(op.f("ix_districts_slug"), table_name="districts")
    op.drop_index(op.f("ix_districts_neighborhood_id"), table_name="districts")
    op.drop_table("districts")
