"""add accounts, account_keys, balance_anchors, statement_accounts; link transactions to their section

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-02 (reworked 2026-10-03)

Epic 13 (Account Balance at a Point in Time). See
aidlc-docs/inception/requirements/account-balance-requirements.md (including its "Scope
Change" section) and aidlc-docs/construction/database/functional-design/ (BR-30..BR-38).

Reworked in place on 2026-10-03 for the several-accounts-per-PDF design: a statement can
hold several accounts, so `bank_statements` is NOT changed. The closing balance and the
account link live on a new `statement_accounts` table (one row per account per
statement), and `transactions` gains a nullable `statement_account_id`. This migration
had only ever run in disposable test databases (the live database was verified at 0018),
which is why it could be rewritten instead of followed by a 0020.

Purely additive -- no existing column, row, or constraint is changed. Existing statements
and transactions keep working unchanged: they have no sections, and
`transactions.statement_account_id` is NULL, until the one-time backfill (US-13.7)
re-ingests them.

Four new tables, created from Base.metadata (same technique as 0004/0013, which also
avoids the known SQLAlchemy/Alembic double-CREATE-TYPE bug for the `accounttype` enum).
BR-30's NULLS NOT DISTINCT unique constraint and BR-33/BR-37 are declared on the models
themselves, so that technique creates them here too -- there is no raw-SQL partial index
in this migration, unlike 0001 (BR-10) and 0004 (BR-14).

`transactions` gains `statement_account_id`, a composite foreign key
(`bank_statement_id`, `statement_account_id`) -> `statement_accounts`
(`bank_statement_id`, `id`) that forces a transaction's section to belong to the
transaction's own statement (BR-38; inert while the column is NULL), and an index. The
foreign keys to `accounts` and `statement_accounts` are ON DELETE RESTRICT (BR-35/BR-36).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from transactagent_db.models import Base

# revision identifiers, used by Alembic.
revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_TABLE_NAMES = ["accounts", "account_keys", "balance_anchors", "statement_accounts"]
_SAME_STATEMENT_FK = "fk_transactions_statement_account_same_statement"


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in _NEW_TABLE_NAMES]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)

    op.add_column(
        "transactions",
        sa.Column("statement_account_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        _SAME_STATEMENT_FK,
        "transactions",
        "statement_accounts",
        ["bank_statement_id", "statement_account_id"],
        ["bank_statement_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_transactions_statement_account_id", "transactions", ["statement_account_id"])


def downgrade() -> None:
    op.drop_index("ix_transactions_statement_account_id", table_name="transactions")
    op.drop_constraint(_SAME_STATEMENT_FK, "transactions", type_="foreignkey")
    op.drop_column("transactions", "statement_account_id")

    bind = op.get_bind()
    for name in reversed(_NEW_TABLE_NAMES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
    # Dropping the table does not drop its enum type (found by live verification).
    op.execute("DROP TYPE IF EXISTS accounttype")
