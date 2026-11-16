"""ingestion run files: skipped_no_activity, skipped_not_a_pdf and a skip_reason column

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-16

Owner request after issue #70: the Drive scan reports what it skips, and a statement with
no transactions at all stops counting as a failure. See
aidlc-docs/construction/plans/drive-scan-skips-and-no-activity-plan.md and BR-54.

`ingestion_run_files.outcome` gains `skipped_no_activity` and `skipped_not_a_pdf`, and the
table gains a nullable `skip_reason` text column with a CHECK that those two outcomes carry
one. PostgreSQL does not let a value added to an enum be used in the transaction that added
it, and the CHECK mentions the new values, so they are added inside autocommit_block()
(committing them) first, as in 0020. Nothing existing changes: every current run file keeps
its outcome and gets a NULL skip_reason.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CHECK = "ck_ingestion_run_files_skip_requires_reason"
_NEW_VALUES = ("skipped_no_activity", "skipped_not_a_pdf")


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for value in _NEW_VALUES:
            op.execute(f"ALTER TYPE ingestionrunfileoutcome ADD VALUE IF NOT EXISTS '{value}'")

    op.add_column("ingestion_run_files", sa.Column("skip_reason", sa.Text(), nullable=True))
    op.create_check_constraint(
        _CHECK,
        "ingestion_run_files",
        "outcome NOT IN ('skipped_no_activity', 'skipped_not_a_pdf') OR skip_reason IS NOT NULL",
    )


def downgrade() -> None:
    # PostgreSQL has no ALTER TYPE ... DROP VALUE (see 0005), so the enum values stay. A run
    # file still using one could not be read back by the pre-0023 models, so refuse rather than
    # leave such rows behind.
    in_use = op.get_bind().execute(
        sa.text(
            "SELECT count(*) FROM ingestion_run_files "
            "WHERE outcome IN ('skipped_no_activity', 'skipped_not_a_pdf')"
        )
    ).scalar()
    if in_use:
        raise RuntimeError(
            f"Cannot downgrade 0023: {in_use} ingestion_run_files row(s) have outcome "
            "'skipped_no_activity' or 'skipped_not_a_pdf'. Delete those rows (or restore a backup "
            "taken before the feature was used) first."
        )
    op.drop_constraint(_CHECK, "ingestion_run_files", type_="check")
    op.drop_column("ingestion_run_files", "skip_reason")
