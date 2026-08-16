"""add setting_changes table

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-16

Configurable Application Settings. See
aidlc-docs/inception/requirements/configurable-app-settings-requirements.md and
aidlc-docs/construction/database/functional-design/ for full design history.

Purely additive -- one new, standalone table (BR-28/BR-29), no FK to any other
entity. Created from Base.metadata (same technique as 0004/0006/0007/0011) to avoid
the known SQLAlchemy/Alembic double-CREATE-TYPE bug for its one enum column
(owning_service).
"""
from typing import Sequence, Union

from alembic import op

from transactagent_db.models import Base

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE_NAME = "setting_changes"


def upgrade() -> None:
    bind = op.get_bind()
    table = Base.metadata.tables[_TABLE_NAME]
    Base.metadata.create_all(bind=bind, tables=[table], checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    table = Base.metadata.tables[_TABLE_NAME]
    table.drop(bind=bind, checkfirst=True)
