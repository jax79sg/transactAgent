"""add backup_runs table

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-08

Epic 7 (Nightly Transaction Backup). See
aidlc-docs/inception/requirements/nightly-backup-requirements.md and
aidlc-docs/construction/database/functional-design/ for full design history.

Creates the table from Base.metadata (same technique as 0004_recategorization_proposals.py),
not hand-written op.create_table() with inline sa.Enum() columns: this table has two enum
columns (outcome, failure_category), and hand-writing them in the same op.create_table() call
hits the same known SQLAlchemy/Alembic double-CREATE-TYPE bug documented in 0004.
Base.metadata.create_all() resolves enum-type creation dependencies itself.
"""
from typing import Sequence, Union

from alembic import op

from transactagent_db.models import Base

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE_NAME = "backup_runs"


def upgrade() -> None:
    bind = op.get_bind()
    table = Base.metadata.tables[_TABLE_NAME]
    Base.metadata.create_all(bind=bind, tables=[table], checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    table = Base.metadata.tables[_TABLE_NAME]
    table.drop(bind=bind, checkfirst=True)
