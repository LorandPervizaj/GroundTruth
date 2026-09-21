"""add listing lifecycle states

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "h2i3j4k5l6m7"
down_revision: str | None = "g1h2i3j4k5l6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "listing_lifecycle_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_website", sa.String(100), nullable=False),
        sa.Column("source_listing_id", sa.String(255), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_run_id", sa.Integer(), nullable=True),
        sa.Column("consecutive_successful_misses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="UNKNOWN"),
        sa.Column("inactive_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_website", "source_listing_id", name="uq_lifecycle_source_listing"),
    )
    op.create_index("ix_lifecycle_source", "listing_lifecycle_states", ["source_website"])
    op.create_index("ix_lifecycle_status", "listing_lifecycle_states", ["status"])
    op.create_index("ix_lifecycle_last_seen_run", "listing_lifecycle_states", ["last_seen_run_id"])


def downgrade() -> None:
    op.drop_table("listing_lifecycle_states")
