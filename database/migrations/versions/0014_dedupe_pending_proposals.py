"""dedupe pending recategorization proposals per candidate

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-23

Issue #12: find_unsure_transactions() (ingestion-worker/categorization/repository.py)
had no exclusion for a candidate that already had a pending proposal from an earlier
RecategorizationJob -- a fresh job (one per manual correction, see
transactions/service.py's correct_transaction_category) re-scanned the whole UNSURE
pool from scratch every time and re-proposed the same recurring-looking candidate
again and again, since a still-UNSURE transaction stays UNSURE (and so keeps showing
up in the scan) until its pending proposal is actually resolved. Live databases can
already have several duplicate pending proposals for the same candidate_transaction_id
from before that code fix landed -- this migration cleans those up and tightens the
constraint that should have caught it from the start.

BR-14's existing partial unique index (0004_recategorization_proposals.py) only
covers (candidate_transaction_id, recategorization_job_id) -- i.e. at most one
pending proposal *per job* for a candidate, which can't even happen naturally since
each job's scan visits each candidate once. It never constrained a DIFFERENT job
proposing the same candidate again. Replaced here with a broader index on
candidate_transaction_id alone (still scoped to status='pending', so a candidate can
freely get a new proposal once its old one is approved/rejected/auto-applied).

Data cleanup must run BEFORE the new index is created, since CREATE UNIQUE INDEX
fails if duplicate pending rows still exist. For each candidate_transaction_id with
more than one pending proposal, keeps the one with the highest match_score (ties
broken by most recent), and marks the rest 'rejected' with resolved_at set -- the
same terminal state a user manually rejecting a proposal produces, so nothing else
in the app needs to special-case a "superseded" status. One-way: downgrade restores
the old narrower index but cannot distinguish these cleanup-rejects from proposals a
user genuinely rejected, so it does not attempt to revert the data change.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY candidate_transaction_id
                       ORDER BY match_score DESC, created_at DESC
                   ) AS rn
            FROM recategorization_proposals
            WHERE status = 'pending'
        )
        UPDATE recategorization_proposals
        SET status = 'rejected', resolved_at = now()
        WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
        """
    )
    op.execute("DROP INDEX IF EXISTS uq_recategorization_proposals_pending_candidate_per_job")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_recategorization_proposals_pending_candidate
        ON recategorization_proposals (candidate_transaction_id)
        WHERE status = 'pending'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_recategorization_proposals_pending_candidate")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_recategorization_proposals_pending_candidate_per_job
        ON recategorization_proposals (candidate_transaction_id, recategorization_job_id)
        WHERE status = 'pending'
        """
    )
