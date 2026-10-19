"""reset embedding_status to pending on all existing rows (re-embed after "Card Payment" boilerplate-phrase stripping text change)

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-29

Recategorization Algorithm Rework, WR-40 (Ingestion Worker unit's business-rules.md),
added retroactively to the Database unit -- same precedent as 0012 and 0016, which
did the equivalent reset the previous two times the embedding text format changed.
Found via interactive live trials: the generic "Card Payment" card-transaction
suffix was dominating embedding similarity across unrelated merchants (e.g.
"MISTER MINIT ARC Card Payment" scoring higher against "AMAZON MKTPLC Card Payment"
than a genuine same-merchant precedent scored against its own query). build_embedding_text
now also strips this phrase wherever it occurs. Every row already at
embedding_status='completed' has a stale vector reflecting neither this change nor
0016's, so this one-time data migration resets every row back to 'pending' -- the
existing processNextEmbeddingBatch() poll-cycle mechanism (WR-26, now concurrent
per WR-40) re-embeds them the same way it already handles brand-new rows.

Explicit constraint (same as 0016/WR-39): this migration touches embedding_status
only. It MUST NOT and does NOT touch category_id, category_source, or any other
column -- assigned categories are completely unaffected, by construction (a plain
single-column UPDATE, nothing else).

Deliberately a plain UPDATE, not a schema change -- downgrade is a genuine no-op,
same reasoning as 0012/0016.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0017"
down_revision: Union[str, None] = "0016"
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
