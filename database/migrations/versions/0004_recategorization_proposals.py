"""add recategorization_proposals table

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-02

Epic 6 (Recategorization Review Panel). See
aidlc-docs/inception/requirements/recategorization-review-requirements.md and
aidlc-docs/construction/database/functional-design/ for full design history.

Creates the table from Base.metadata (same technique as 0001_initial_schema.py's
_INITIAL_TABLE_NAMES-scoped create_all), rather than hand-writing op.create_table()
with inline sa.Enum() columns: this table has two enum columns (source_bucket,
status), and hand-writing them as separate sa.Enum(...) objects in the same
op.create_table() call hits a real SQLAlchemy/Alembic bug where the second enum's
CREATE TYPE statement fires twice, raising `DuplicateObject` -- caught by actually
running `alembic upgrade head` against a live Postgres, not by the unit test suite
(which builds its schema via Base.metadata.create_all() directly, bypassing this
file entirely -- see database/tests/test_models.py's TestRecategorizationProposal
docstring). Base.metadata.create_all() does not have this bug since it resolves
enum-type creation dependencies itself.
"""
from typing import Sequence, Union

from alembic import op

from transactagent_db.models import Base

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE_NAME = "recategorization_proposals"


def upgrade() -> None:
    bind = op.get_bind()
    table = Base.metadata.tables[_TABLE_NAME]
    Base.metadata.create_all(bind=bind, tables=[table], checkfirst=True)

    # BR-14: at most one 'pending' proposal per (candidate_transaction_id,
    # recategorization_job_id) pair. Same partial-unique-index pattern as BR-10 on
    # ingestion_runs (0001_initial_schema.py) -- not representable via standard
    # SQLAlchemy Table/Column metadata, so added here as raw SQL.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_recategorization_proposals_pending_candidate_per_job
        ON recategorization_proposals (candidate_transaction_id, recategorization_job_id)
        WHERE status = 'pending'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_recategorization_proposals_pending_candidate_per_job")
    bind = op.get_bind()
    table = Base.metadata.tables[_TABLE_NAME]
    table.drop(bind=bind, checkfirst=True)
