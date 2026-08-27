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

    # Same class of bug as 0001's fresh-database drift fix (see that migration's
    # upgrade() for the full explanation): Base.metadata.create_all() above reflects
    # the CURRENT recurring_payments model, which already includes embedding_status --
    # a column actually introduced later, by 0010's own op.add_column(). Drop it here
    # so 0010 remains the single source of truth for it and the full chain replays
    # correctly from an empty database. Found via the same real fresh-database
    # Kubernetes deployment attempt that surfaced 0001's version of this bug
    # (2026-08-21) -- this was the very next failure once 0001 was fixed, from this
    # exact same root cause recurring at a second, independent call site.
    op.drop_column("recurring_payments", "embedding_status")  # actually added by 0010

    # Same fresh-database drift, found again (2026-08-27) the very next time a new
    # column was added to either of these two models: due_soon_lead_days
    # (RecurringPayment) and detected_frequency/suggested_due_month/
    # suggested_due_day (DetectionSuggestion) are all actually added by 0015, not
    # here -- Base.metadata.create_all() above already reflects the current model
    # state, so all four must be dropped here for the same reason embedding_status
    # is, above.
    op.drop_column("recurring_payments", "due_soon_lead_days")  # actually added by 0015
    op.drop_column("detection_suggestions", "detected_frequency")  # actually added by 0015
    op.drop_column("detection_suggestions", "suggested_due_month")  # actually added by 0015
    op.drop_column("detection_suggestions", "suggested_due_day")  # actually added by 0015

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
