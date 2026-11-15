"""give accounts whose identifier is a name the name they should have had

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-15

Issue #66. GXS prints a pocket's name where other banks print an account number, so the worker's default account
name (`<bank> <last 4 characters of the identifier>`) turned "AlphaBoostPocket" and "BetaBoostPocket" into the same
"GXS Bank cket". The worker now names such accounts from the whole identifier, in words ("GXS Bank Alpha Boost Pocket");
this renames the ones already created.

Deliberately narrow, because it edits rows the owner can see:
  * only an account whose name is still EXACTLY the old default (`<bank_name> <last 4 of the identifier>`): a name the
    owner typed is never touched;
  * only when the identifier is a name, by the same test as the worker (a lowercase letter and fewer than 4 digits),
    so no real or masked account number is renamed;
  * only an account with exactly one key (a merged account has several, and which one named it is unknowable).
It is idempotent (a renamed account no longer matches) and cosmetic, so the downgrade does nothing: the old name was the
bug, and nobody can tell which accounts the owner would want it back on.

The three substitutions that turn an identifier into words are the worker's `identifier_in_words`, in SQL;
ingestion-worker/tests/test_account_name_migration.py checks the two agree on a real database.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_IN_WORDS = (
    r"regexp_replace(regexp_replace(regexp_replace(k.account_identifier,"
    r" '([a-z])([A-Z])', '\1 \2', 'g'),"
    r" '([A-Za-z])([0-9])', '\1 \2', 'g'),"
    r" '([0-9])([A-Za-z])', '\1 \2', 'g')"
)

RENAME_NAME_LIKE_ACCOUNTS = f"""
UPDATE accounts AS a
SET name = a.bank_name || ' ' || {_IN_WORDS}, updated_at = now()
FROM account_keys AS k
WHERE k.account_id = a.id
  AND k.account_identifier ~ '[a-z]'
  AND length(regexp_replace(k.account_identifier, '[^0-9]', '', 'g')) < 4
  AND a.name = a.bank_name || ' ' || right(k.account_identifier, 4)
  AND (SELECT count(*) FROM account_keys AS other WHERE other.account_id = a.id) = 1
  AND a.name <> a.bank_name || ' ' || {_IN_WORDS}
"""


def rename_name_like_accounts(connection) -> int:
    """Returns how many accounts were renamed."""
    return connection.execute(sa.text(RENAME_NAME_LIKE_ACCOUNTS)).rowcount


def upgrade() -> None:
    rename_name_like_accounts(op.get_bind())


def downgrade() -> None:
    """Nothing to undo: see the module docstring."""
