"""add recurring payments, matches, and detection suggestions tables

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-08

Epic 8 (Recurring Payments, Budget Alerts & Subscription Detection). See
aidlc-docs/inception/requirements/recurring-payments-requirements.md and
aidlc-docs/construction/database/functional-design/ for full design history.

Creates all 3 tables from Base.metadata (same technique as 0004/0006), not
hand-written op.create_table() with inline sa.Enum() columns, to avoid the known
SQLAlchemy/Alembic double-CREATE-TYPE bug documented in 0004 -- each table here only
has one enum column, but this keeps the pattern consistent and risk-free regardless.
"""
from typing import Sequence, Union

from alembic import op

from transactagent_db.models import Base

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE_NAMES = ["recurring_payments", "recurring_payment_matches", "detection_suggestions"]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in _TABLE_NAMES]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)

    # BR-21: at most one "live" (non-rejected) match per (recurring_payment_id,
    # cycle_period) pair. Same partial-unique-index pattern as BR-10 (0001) and
    # BR-14 (0004) -- not representable via standard SQLAlchemy Table/Column
    # metadata, so added here as raw SQL.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_recurring_payment_matches_live_per_cycle
        ON recurring_payment_matches (recurring_payment_id, cycle_period)
        WHERE status != 'rejected'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_recurring_payment_matches_live_per_cycle")
    bind = op.get_bind()
    # Drop in reverse FK dependency order.
    for name in reversed(_TABLE_NAMES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
