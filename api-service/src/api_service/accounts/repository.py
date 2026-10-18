"""Data access for Account Management (Epic 13, AR-51 to AR-54, AR-65). Reads and the four writes the feature makes:
account name and type, the anchor, and a merge (statement sections, keys, anchor, the emptied account). Nothing
else is ever written (AR-67)."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from transactagent_db.models import (
    Account,
    AccountKey,
    BalanceAnchor,
    StatementAccount,
    Transaction,
)


@dataclass(frozen=True)
class AccountListRow:
    account: Account
    anchor: BalanceAnchor | None
    account_identifier: str | None
    statement_count: int
    closing_balance_count: int
    transaction_count: int
    latest_transaction_date: date | None


def list_account_rows(db: Session) -> list[AccountListRow]:
    """Every account with its anchor and the figures the account screen shows, in four reads (not one per account)."""
    base = db.execute(
        select(Account, BalanceAnchor).outerjoin(BalanceAnchor, BalanceAnchor.account_id == Account.id)
    ).all()

    sections = {
        account_id: (statements, closings)
        for account_id, statements, closings in db.execute(
            select(
                StatementAccount.account_id,
                func.count(StatementAccount.id),
                func.count(StatementAccount.closing_balance),
            ).group_by(StatementAccount.account_id)
        ).all()
    }
    activity = {
        account_id: (count, latest)
        for account_id, count, latest in db.execute(
            select(StatementAccount.account_id, func.count(Transaction.id), func.max(Transaction.transaction_date))
            .join(Transaction, Transaction.statement_account_id == StatementAccount.id)
            .group_by(StatementAccount.account_id)
        ).all()
    }
    identifiers: dict[UUID, str] = {}
    for account_id, identifier in db.execute(
        select(AccountKey.account_id, AccountKey.account_identifier)
        .where(AccountKey.account_identifier.is_not(None))
        .order_by(AccountKey.account_id, AccountKey.created_at, AccountKey.id)
    ).all():
        identifiers.setdefault(account_id, identifier)

    return [
        AccountListRow(
            account=account,
            anchor=anchor,
            account_identifier=identifiers.get(account.id),
            statement_count=sections.get(account.id, (0, 0))[0],
            closing_balance_count=sections.get(account.id, (0, 0))[1],
            transaction_count=activity.get(account.id, (0, None))[0],
            latest_transaction_date=activity.get(account.id, (0, None))[1],
        )
        for account, anchor in base
    ]


def get_account_row(db: Session, account_id: UUID) -> AccountListRow | None:
    return next((row for row in list_account_rows(db) if row.account.id == account_id), None)


def get_account(db: Session, account_id: UUID) -> Account | None:
    return db.get(Account, account_id)


def lock_accounts(db: Session, account_ids: list[UUID]) -> dict[UUID, Account]:
    """The named accounts, locked for update in id order so two merges can never deadlock (AR-65)."""
    rows = db.scalars(select(Account).where(Account.id.in_(account_ids)).order_by(Account.id).with_for_update()).all()
    return {account.id: account for account in rows}


def get_anchor(db: Session, account_id: UUID) -> BalanceAnchor | None:
    return db.scalar(select(BalanceAnchor).where(BalanceAnchor.account_id == account_id))


def upsert_anchor(db: Session, account_id: UUID, balance: Decimal, as_of_date: date) -> BalanceAnchor:
    """Create or replace the account's single anchor in one conditional write (BR-32, AR-53)."""
    statement = pg_insert(BalanceAnchor).values(account_id=account_id, balance=balance, as_of_date=as_of_date)
    db.execute(
        statement.on_conflict_do_update(
            index_elements=[BalanceAnchor.account_id],
            set_={"balance": statement.excluded.balance, "as_of_date": statement.excluded.as_of_date, "updated_at": func.now()},
        )
    )
    db.expire_all()
    return db.scalars(select(BalanceAnchor).where(BalanceAnchor.account_id == account_id)).one()


def statement_lists_both(db: Session, first: UUID, second: UUID) -> bool:
    """True when some statement has a section for each account: proof they are different accounts (AR-54)."""
    found = db.scalar(
        select(StatementAccount.bank_statement_id)
        .where(StatementAccount.account_id.in_([first, second]))
        .group_by(StatementAccount.bank_statement_id)
        .having(func.count(func.distinct(StatementAccount.account_id)) == 2)
        .limit(1)
    )
    return found is not None


def repoint_sections(db: Session, from_account: UUID, to_account: UUID) -> int:
    return db.execute(
        update(StatementAccount).where(StatementAccount.account_id == from_account).values(account_id=to_account)
    ).rowcount


def repoint_keys(db: Session, from_account: UUID, to_account: UUID) -> int:
    return db.execute(update(AccountKey).where(AccountKey.account_id == from_account).values(account_id=to_account)).rowcount


def delete_anchor(db: Session, account_id: UUID) -> None:
    db.execute(delete(BalanceAnchor).where(BalanceAnchor.account_id == account_id))


def move_anchor(db: Session, from_account: UUID, to_account: UUID) -> None:
    db.execute(update(BalanceAnchor).where(BalanceAnchor.account_id == from_account).values(account_id=to_account))


def delete_account(db: Session, account_id: UUID) -> None:
    db.execute(delete(Account).where(Account.id == account_id))
