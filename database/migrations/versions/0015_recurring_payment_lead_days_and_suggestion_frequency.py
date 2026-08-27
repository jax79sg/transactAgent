"""add recurring_payments.due_soon_lead_days and detection_suggestions frequency/due fields

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-27

Issue #15 (Recurring payment overhaul): a single global due-soon lead-time setting
couldn't give an annual bill meaningfully more advance notice than a monthly one --
`due_soon_lead_days` lets one specific payment override its frequency's own default
(NULL means "use the frequency-based default", see recurring_payments/service.py's
_compute_status_and_set_aside). `detected_frequency` records which cadence the
detection scan actually matched (monthly or annual, see ingestion_worker/
recurring_payments/service.py's _has_monthly_cadence/_has_annual_cadence), so
add_from_detection_suggestion can default a new payment's frequency correctly
instead of always hardcoding "monthly". `suggested_due_month`/`suggested_due_day`
record the most recent detected occurrence's actual calendar day, so a new payment
created from a suggestion defaults to when the pattern actually happens rather than
"whatever day the user happens to click Add" (the previous behavior for due_day,
date.today().day -- due_month had no default path at all before this, since
detection was monthly-only until this same change).

detected_frequency reuses the existing recurringpaymentfrequency Postgres enum type
(created when recurring_payments.frequency was added in 0007, via
Base.metadata.create_all) -- create_type=False, no explicit .create() call, since
that type is guaranteed to already exist by the time this migration runs.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ENUM_NAME = "recurringpaymentfrequency"


def upgrade() -> None:
    op.add_column("recurring_payments", sa.Column("due_soon_lead_days", sa.Integer(), nullable=True))

    frequency_enum = postgresql.ENUM("monthly", "annual", name=_ENUM_NAME, create_type=False)
    op.add_column("detection_suggestions", sa.Column("detected_frequency", frequency_enum, nullable=True))
    op.add_column("detection_suggestions", sa.Column("suggested_due_month", sa.Integer(), nullable=True))
    op.add_column("detection_suggestions", sa.Column("suggested_due_day", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("detection_suggestions", "suggested_due_day")
    op.drop_column("detection_suggestions", "suggested_due_month")
    op.drop_column("detection_suggestions", "detected_frequency")
    op.drop_column("recurring_payments", "due_soon_lead_days")
