"""Account/AccountKey persistence for the Account Resolver (WR-49)."""

from sqlalchemy import select
from sqlalchemy.orm import Session
from transactagent_db.models import Account, AccountKey, AccountType


def find_account_by_key(db: Session, bank_key: str, account_identifier: str | None, currency: str) -> Account | None:
    """BR-30 guarantees at most one key per (bank_key, identifier, currency), where a
    missing identifier counts as its own value -- hence the explicit IS NULL branch."""
    identifier_match = (
        AccountKey.account_identifier.is_(None)
        if account_identifier is None
        else AccountKey.account_identifier == account_identifier
    )
    return db.scalar(
        select(Account)
        .join(AccountKey, AccountKey.account_id == Account.id)
        .where(AccountKey.bank_key == bank_key, identifier_match, AccountKey.currency == currency)
    )


def create_account_with_key(
    db: Session,
    *,
    name: str,
    bank_name: str,
    account_type: AccountType,
    currency: str,
    bank_key: str,
    account_identifier: str | None,
) -> Account:
    account = Account(name=name, bank_name=bank_name, account_type=account_type, currency=currency)
    db.add(account)
    db.flush()
    db.add(AccountKey(account_id=account.id, bank_key=bank_key, account_identifier=account_identifier, currency=currency))
    db.flush()
    return account
