"""add detection_scan_runs table

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-08

Epic 8 (Recurring Payments) -- added retroactively during Ingestion Worker Code
Generation after finding no entity backed `isDetectionScanDueNow()`'s due-check
(services.md's poll_once() addendum already assumed this shape existed). See
aidlc-docs/audit.md for the full history.

Single-column table, no enum columns -- op.create_table() is safe to hand-write
here (the double-CREATE-TYPE bug in 0004's docstring only applies to multi-enum
tables), but uses the same Base.metadata technique as every other migration since
0004 for consistency.
"""
from typing import Sequence, Union

from alembic import op

from transactagent_db.models import Base

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE_NAME = "detection_scan_runs"


def upgrade() -> None:
    bind = op.get_bind()
    table = Base.metadata.tables[_TABLE_NAME]
    Base.metadata.create_all(bind=bind, tables=[table], checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    table = Base.metadata.tables[_TABLE_NAME]
    table.drop(bind=bind, checkfirst=True)
