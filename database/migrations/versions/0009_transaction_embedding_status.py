"""add transactions.embedding_status

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-11

Epic 9 (Local Embedding-Based Semantic Similarity). BR-24: one-way, two-state
column (pending -> completed, no failed state) on the existing `transactions`
table. `server_default='pending'` is what makes forward processing and the
one-time historical backfill (FR-11) the same mechanism -- every pre-existing row
gets backfilled to 'pending' by this migration itself, no separate UPDATE/backfill
script needed. See aidlc-docs/construction/database/functional-design/ for the full
design history.

Adding a single new enum column via op.add_column() (not Base.metadata.create_all,
which 0004/0008 use for whole-table creation) -- explicitly `.create()`ing the
Postgres ENUM type first and passing `create_type=False` to add_column avoids the
double-CREATE-TYPE issue documented in 0004's docstring (that bug was specific to
multiple enum columns in one op.create_table() call; a single add_column() doesn't
hit it, but creating the type explicitly keeps the pattern consistent and obvious).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ENUM_NAME = "embeddingstatus"


def upgrade() -> None:
    embedding_status_enum = postgresql.ENUM("pending", "completed", name=_ENUM_NAME, create_type=False)
    embedding_status_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "transactions",
        sa.Column(
            "embedding_status",
            embedding_status_enum,
            nullable=False,
            server_default="pending",
        ),
    )


def downgrade() -> None:
    op.drop_column("transactions", "embedding_status")
    op.execute(f"DROP TYPE IF EXISTS {_ENUM_NAME}")
