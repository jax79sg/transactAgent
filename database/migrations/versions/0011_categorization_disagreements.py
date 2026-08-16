"""add transactions.llm_suggested_category_id and categorization_disagreements table

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-16

Matching Precision Refinement. See
aidlc-docs/inception/requirements/matching-precision-refinement-requirements.md and
aidlc-docs/construction/database/functional-design/ for full design history.

Two changes bundled here, same precedent as 0007 bundling 3 related tables in one
migration: (1) transactions.llm_suggested_category_id (BR-26) -- a plain nullable FK
column, no enum type involved, added via op.add_column; (2) the new
categorization_disagreements table (BR-27), created from Base.metadata (same
technique as 0004/0006/0007) to avoid the known SQLAlchemy/Alembic double-CREATE-TYPE
bug for its one enum column (status).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

from transactagent_db.models import Base

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE_NAME = "categorization_disagreements"


def upgrade() -> None:
    # BR-26: write-once, nullable (null = LLM abstained or endpoint unreachable at
    # ingestion time). No server_default -- unlike embedding_status, there is no
    # "not yet processed" meaning to backfill; every pre-existing transaction simply
    # stays null, which is exactly what "the LLM never classified this one" means.
    op.add_column(
        "transactions",
        sa.Column(
            "llm_suggested_category_id",
            UUID(as_uuid=True),
            sa.ForeignKey("categories.id"),
            nullable=True,
        ),
    )

    bind = op.get_bind()
    table = Base.metadata.tables[_TABLE_NAME]
    Base.metadata.create_all(bind=bind, tables=[table], checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    table = Base.metadata.tables[_TABLE_NAME]
    table.drop(bind=bind, checkfirst=True)

    op.drop_column("transactions", "llm_suggested_category_id")
