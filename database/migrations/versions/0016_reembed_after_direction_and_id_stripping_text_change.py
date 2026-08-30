"""reset embedding_status to pending on all existing rows (re-embed after direction signal + reference-code stripping text change)

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-28

Recategorization Algorithm Rework, WR-39 (Ingestion Worker unit's business-rules.md),
added retroactively to the Database unit -- same precedent as
0012_reembed_after_price_bucket_text_change.py, which did the equivalent reset the
last time the embedding text format changed (WR-29's price-bucket addition). This
feature changes the text every embedding is computed from again: an in-flow/out-flow
direction token is appended (WR-36) and known reference-code/boilerplate noise is
stripped before embedding (WR-37). Every row already at embedding_status='completed'
has a stale vector reflecting neither change, so this one-time data migration resets
every row back to 'pending' -- the existing processNextEmbeddingBatch() poll-cycle
mechanism (WR-26) then re-embeds them the same way it already handles brand-new rows,
no separate code path needed.

Explicit constraint (WR-39): this migration touches embedding_status only. It MUST
NOT and does NOT touch category_id, category_source, or any other column -- assigned
categories are completely unaffected by this backfill, by construction (a plain
single-column UPDATE, nothing else).

Deliberately a plain UPDATE, not a schema change -- downgrade is a genuine no-op, same
reasoning as 0012: there is no prior state to restore.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: Union[str, None] = "0015"
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
