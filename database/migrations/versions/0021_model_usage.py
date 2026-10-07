"""add model_usage, the ledger behind the Costs page

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-07

Issue #28 (Model Cost Page). See aidlc-docs/inception/requirements/model-cost-page-requirements.md.

Purely additive: one new standalone table, no existing column, row or constraint touched. Created from
Base.metadata, the same technique as 0004/0013/0019/0020 (the table, its CHECK constraints and its index are all
declared on the model). It has no enum column, so none of the CREATE TYPE care the earlier migrations take.
Downgrading drops the table and the spend history in it, so it refuses while the table holds rows unless the
caller deletes them first (the same refuse-rather-than-destroy rule as 0020).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from transactagent_db.models import Base

# revision identifiers, used by Alembic.
revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), tables=[Base.metadata.tables["model_usage"]], checkfirst=True)


def downgrade() -> None:
    rows = op.get_bind().execute(sa.text("SELECT count(*) FROM model_usage")).scalar()
    if rows:
        raise RuntimeError(
            f"Cannot downgrade 0021: model_usage holds {rows} row(s) of spend history, which dropping the "
            "table would destroy. Delete the rows (or take a backup you accept restoring) first."
        )
    Base.metadata.tables["model_usage"].drop(bind=op.get_bind(), checkfirst=True)
