"""reset embedding_status to pending on all existing rows (re-embed after PayNow-Mobile reference-noise-stripping exemption text change)

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-29

Recategorization Algorithm Rework, WR-41 (Ingestion Worker unit's business-rules.md),
added retroactively to the Database unit -- same precedent as 0012, 0016, and 0017,
which did the equivalent reset the previous three times the embedding text format
changed. Found via interactive live trials: PayNow-Mobile (person-to-person) transfer
descriptions were having their OTHR-/REF: suffix stripped as if it were reference-code
noise (WR-37), when for this transfer type it's often a genuine free-text note the
user relied on to categorize the transfer (e.g. "OTHR-gold bar" vs. "OTHR-shanghai
trip"). build_embedding_text now skips that stripping specifically for PayNow-Mobile
descriptions. Every row already at embedding_status='completed' has a stale vector
reflecting neither this change nor 0016's/0017's, so this one-time data migration
resets every row back to 'pending' -- the existing processNextEmbeddingBatch()
poll-cycle mechanism (WR-26, concurrent per WR-40) re-embeds them the same way it
already handles brand-new rows.

Explicit constraint (same as 0016/0017, WR-39): this migration touches
embedding_status only. It MUST NOT and does NOT touch category_id, category_source,
or any other column -- assigned categories are completely unaffected, by
construction (a plain single-column UPDATE, nothing else).

Note: WR-42 (the same live-trial session's threshold recalibration,
embedding_similarity_threshold 0.82 -> 0.92) does NOT require a migration -- it
changes how stored vectors are compared, not what they were computed from, so no
existing vector is stale because of it.

Deliberately a plain UPDATE, not a schema change -- downgrade is a genuine no-op,
same reasoning as 0012/0016/0017.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018"
down_revision: Union[str, None] = "0017"
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
