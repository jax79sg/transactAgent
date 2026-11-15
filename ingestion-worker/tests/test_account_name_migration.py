"""Issue #66: migration 0022 (SQL) and `default_account_name` (Python) are two implementations of one rule, so they
must agree. The migration renames an old-style default name to what the worker would name the account today, and
leaves every account the worker would not rename exactly as it was."""

import importlib.util
from pathlib import Path

import pytest
from transactagent_db.models import Account, AccountKey, AccountType

from ingestion_worker.accounts.normalize import (
    default_account_name,
    identifier_is_a_name,
)

_MIGRATION = Path(__file__).resolve().parents[2] / "database" / "migrations" / "versions" / "0022_rename_name_like_accounts.py"

# Names, numbers, masks and the awkward ones between them.
_IDENTIFIERS = [
    "AlphaBoostPocket",
    "BetaBoostPocket",
    "SavingsPocket2",
    "Boost2Pocket",
    "MyPocketA1B2",
    "pocket",
    "abc123",
    "ABCpocket",
    "411111****1234",
    "4111111111111111",
    "XXXXXXXX",
    "1111222233",
    "AB12CD34",
    "12",
]


@pytest.fixture(scope="module")
def migration():
    spec = importlib.util.spec_from_file_location("migration_0022", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("identifier", _IDENTIFIERS)
def test_the_migration_gives_the_name_the_worker_would_give_today(db_session, migration, identifier):
    bank = "Some Bank"
    old_default_name = f"{bank} {identifier[-4:]}"  # what the worker used to name every account
    account = Account(name=old_default_name, bank_name=bank, account_type=AccountType.DEPOSIT, currency="SGD")
    db_session.add(account)
    db_session.flush()
    db_session.add(AccountKey(account_id=account.id, bank_key="some", account_identifier=identifier, currency="SGD"))
    db_session.flush()

    migration.rename_name_like_accounts(db_session.connection())
    db_session.expire_all()

    if identifier_is_a_name(identifier):
        assert account.name == default_account_name(bank, identifier)
    else:
        assert account.name == old_default_name
