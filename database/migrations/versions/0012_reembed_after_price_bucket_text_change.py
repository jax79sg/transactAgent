"""reset embedding_status to pending on all existing rows (re-embed after price-bucket text change)

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-16

Matching Precision Refinement, WR-32 (Ingestion Worker unit's business-rules.md),
added retroactively to the Database unit -- same precedent as
0010_recurring_payment_embedding_status.py being added retroactively during Epic
9's Ingestion Worker Functional Design. The text every embedding is computed from
now includes a price-range bucket (WR-29); every row already at
embedding_status='completed' has a stale vector missing that bucket, so this
one-time data migration resets every row back to 'pending' -- the existing
processNextEmbeddingBatch() poll-cycle mechanism (WR-26) then re-embeds them the
same way it already handles brand-new rows, no separate code path needed.

Deliberately a plain UPDATE, not a schema change -- downgrade is a genuine no-op
(there is no prior state to restore: rows that were already 'completed' before this
migration ran are, by definition, exactly the rows this migration resets, and
Alembic downgrades don't reconstruct "what a row's status was before an unrelated
migration" from nothing).
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE transactions SET embedding_status = 'pending' WHERE embedding_status = 'completed'")
    op.execute("UPDATE recurring_payments SET embedding_status = 'pending' WHERE embedding_status = 'completed'")


def downgrade() -> None:
    # No-op by design -- see module docstring. Nothing to reverse: this migration
    # only ever moves rows from 'completed' to 'pending', a state the existing
    # embedding poll mechanism (WR-26) is always safe to observe regardless of how
    # a row got there.
    pass
