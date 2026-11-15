"""Migration 0022 (issue #66): rename the accounts that carry the old broken default name, and nothing else."""

import importlib.util
from pathlib import Path

import pytest

from transactagent_db.models import Account, AccountKey, AccountType

_MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0022_rename_name_like_accounts.py"


@pytest.fixture(scope="module")
def migration():
    spec = importlib.util.spec_from_file_location("migration_0022", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _account(db, name, identifier, bank="GXS Bank", extra_identifiers=()):
    account = Account(name=name, bank_name=bank, account_type=AccountType.DEPOSIT, currency="SGD")
    db.add(account)
    db.flush()
    for key_identifier in (identifier, *extra_identifiers):
        db.add(AccountKey(account_id=account.id, bank_key=bank.lower(), account_identifier=key_identifier, currency="SGD"))
    db.flush()
    return account


def _names(db):
    db.expire_all()
    return {a.id: a.name for a in db.query(Account)}


def test_renames_the_pocket_accounts_the_owner_reported(db_session, migration):
    alpha = _account(db_session, "GXS Bank cket", "AlphaBoostPocket")
    beta = _account(db_session, "GXS Bank cket", "BetaBoostPocket")

    renamed = migration.rename_name_like_accounts(db_session.connection())

    names = _names(db_session)
    assert renamed == 2
    assert names[alpha.id] == "GXS Bank Alpha Boost Pocket"
    assert names[beta.id] == "GXS Bank Beta Boost Pocket"


def test_splits_letters_from_digits_too(db_session, migration):
    pocket = _account(db_session, "GXS Bank ket2", "SavingsPocket2")

    migration.rename_name_like_accounts(db_session.connection())

    assert _names(db_session)[pocket.id] == "GXS Bank Savings Pocket 2"


def test_never_touches_a_name_the_owner_chose(db_session, migration):
    mine = _account(db_session, "My pocket", "AlphaBoostPocket")

    renamed = migration.rename_name_like_accounts(db_session.connection())

    assert renamed == 0
    assert _names(db_session)[mine.id] == "My pocket"


def test_never_touches_a_real_or_masked_account_number(db_session, migration):
    real = _account(db_session, "OCBC Bank 5001", "501123456001", bank="OCBC Bank")
    masked = _account(db_session, "MariBank 1234", "411111****1234", bank="MariBank")
    mask_only = _account(db_session, "Some Bank XXXX", "XXXXXXXX", bank="Some Bank")
    no_identifier = _account(db_session, "Trust Bank", None, bank="Trust Bank")

    renamed = migration.rename_name_like_accounts(db_session.connection())

    names = _names(db_session)
    assert renamed == 0
    assert (names[real.id], names[masked.id], names[mask_only.id], names[no_identifier.id]) == (
        "OCBC Bank 5001",
        "MariBank 1234",
        "Some Bank XXXX",
        "Trust Bank",
    )


def test_leaves_a_merged_account_with_several_keys_alone(db_session, migration):
    merged = _account(db_session, "GXS Bank cket", "AlphaBoostPocket", extra_identifiers=("BetaBoostPocket",))

    renamed = migration.rename_name_like_accounts(db_session.connection())

    assert renamed == 0
    assert _names(db_session)[merged.id] == "GXS Bank cket"


def test_is_idempotent(db_session, migration):
    _account(db_session, "GXS Bank cket", "AlphaBoostPocket")

    first = migration.rename_name_like_accounts(db_session.connection())
    second = migration.rename_name_like_accounts(db_session.connection())

    assert (first, second) == (1, 0)
