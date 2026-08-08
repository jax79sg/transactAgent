"""add ingestion run cancellation

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-05

Adds a user-initiated "Cancel" action for an in-progress ingestion run. See
aidlc-docs/audit.md 2026-08-05 for the full design history.

`cancel_requested_at` is written only by the API (on cancel request) and read only
by the worker (checked between files, never mid-file) -- the worker remains the
sole writer of `status`, so the two separate processes never race on the same
column. `cancelled` is a new terminal IngestionRunStatus value.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres 16 allows ALTER TYPE ... ADD VALUE inside a transaction (this
    # restriction was lifted in PG12); the new value just can't be used in the same
    # transaction it's added in, which this migration doesn't need to do.
    op.execute("ALTER TYPE ingestionrunstatus ADD VALUE IF NOT EXISTS 'cancelled'")
    op.add_column(
        "ingestion_runs",
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ingestion_runs", "cancel_requested_at")
    # Postgres has no ALTER TYPE ... DROP VALUE -- removing 'cancelled' from
    # ingestionrunstatus would require rebuilding the enum type (and any column/rows
    # using it), which isn't done here. Any row already in status='cancelled' would
    # need to be resolved to another status before attempting that manually.
