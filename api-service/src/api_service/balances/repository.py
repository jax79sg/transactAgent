"""Read-only data access for balances (Epic 13, AR-55 to AR-62, AR-66). Nothing here writes. Net flows are summed by
the database: transactions are never loaded into memory, only totals (NFR-AB-5)."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from transactagent_db.models import (
    Account,
    AccountType,
    BalanceAnchor,
    FxRateCache,
    StatementAccount,
    Transaction,
)

_FLOW = func.coalesce(Transaction.in_flow, 0) - func.coalesce(Transaction.out_flow, 0)


@dataclass(frozen=True)
class DepositAccountRow:
    id: UUID
    name: str
    bank_name: str
    currency: str
    anchor_balance: Decimal | None
    anchor_date: date | None


@dataclass(frozen=True)
class ClosingRow:
    account_id: UUID
    statement_id: UUID
    balance: Decimal
    closing_date: date
    recorded_order: int


@dataclass(frozen=True)
class UnlinkedSummary:
    count: int
    bank_names: list[str]
    earliest_date: date
    latest_date: date
    net_by_currency: list[tuple[str, Decimal]]


def list_deposit_accounts(db: Session) -> list[DepositAccountRow]:
    """Every deposit account, with its anchor if it has one. Credit cards and unknown types never appear (AR-58)."""
    rows = db.execute(
        select(Account, BalanceAnchor)
        .outerjoin(BalanceAnchor, BalanceAnchor.account_id == Account.id)
        .where(Account.account_type == AccountType.DEPOSIT)
        .order_by(func.lower(Account.name), Account.id)
    ).all()
    return [
        DepositAccountRow(
            id=account.id,
            name=account.name,
            bank_name=account.bank_name,
            currency=account.currency,
            anchor_balance=anchor.balance if anchor else None,
            anchor_date=anchor.as_of_date if anchor else None,
        )
        for account, anchor in rows
    ]


def list_closing_balances(db: Session, account_ids: list[UUID]) -> dict[UUID, list[ClosingRow]]:
    """The printed closing balances of these accounts, one list per account, with a record order (oldest recorded
    first) so that two statements closing on one date are told apart deterministically (AR-55)."""
    rows = db.execute(
        select(
            StatementAccount.account_id,
            StatementAccount.bank_statement_id,
            StatementAccount.closing_balance,
            StatementAccount.closing_balance_date,
        )
        .where(
            StatementAccount.account_id.in_(account_ids),
            StatementAccount.closing_balance.is_not(None),
            StatementAccount.closing_balance_date.is_not(None),
        )
        .order_by(StatementAccount.created_at, StatementAccount.id)
    ).all()
    by_account: dict[UUID, list[ClosingRow]] = {}
    for order, (account_id, statement_id, balance, closing_date) in enumerate(rows):
        by_account.setdefault(account_id, []).append(ClosingRow(account_id, statement_id, balance, closing_date, order))
    return by_account


def net_flow_between(db: Session, account_id: UUID, after: date, through: date) -> Decimal:
    """Inflows minus outflows of the account's transactions dated after `after` up to and including `through`, in the
    account's own currency, summed by the database."""
    total = db.scalar(
        select(func.coalesce(func.sum(_FLOW), 0))
        .join(StatementAccount, StatementAccount.id == Transaction.statement_account_id)
        .where(
            StatementAccount.account_id == account_id,
            Transaction.transaction_date > after,
            Transaction.transaction_date <= through,
        )
    )
    return Decimal(total)


def daily_flow_totals(db: Session, account_ids: list[UUID]) -> dict[UUID, dict[date, Decimal]]:
    """Per account, the net flow of each day that has any: the whole history, as totals, in one read."""
    rows = db.execute(
        select(StatementAccount.account_id, Transaction.transaction_date, func.sum(_FLOW))
        .join(StatementAccount, StatementAccount.id == Transaction.statement_account_id)
        .where(StatementAccount.account_id.in_(account_ids))
        .group_by(StatementAccount.account_id, Transaction.transaction_date)
    ).all()
    totals: dict[UUID, dict[date, Decimal]] = {account_id: {} for account_id in account_ids}
    for account_id, day, total in rows:
        totals[account_id][day] = Decimal(total)
    return totals


def latest_transaction_date_overall(db: Session) -> date | None:
    """The date through which transactions have been ingested: the latest of ALL transactions (FR-AB-14)."""
    return db.scalar(select(func.max(Transaction.transaction_date)))


def latest_transaction_dates_by_account(db: Session, account_ids: list[UUID]) -> dict[UUID, date]:
    rows = db.execute(
        select(StatementAccount.account_id, func.max(Transaction.transaction_date))
        .join(Transaction, Transaction.statement_account_id == StatementAccount.id)
        .where(StatementAccount.account_id.in_(account_ids))
        .group_by(StatementAccount.account_id)
    ).all()
    return dict(rows)


def unlinked_summary(db: Session) -> UnlinkedSummary | None:
    """The transactions linked to no account, which can belong to no balance (AR-60); None when there are none."""
    count, earliest, latest = db.execute(
        select(func.count(Transaction.id), func.min(Transaction.transaction_date), func.max(Transaction.transaction_date)).where(
            Transaction.statement_account_id.is_(None)
        )
    ).one()
    if not count:
        return None
    banks = db.scalars(
        select(Transaction.bank_name).where(Transaction.statement_account_id.is_(None)).distinct().order_by(Transaction.bank_name)
    ).all()
    nets = db.execute(
        select(Transaction.currency, func.sum(_FLOW))
        .where(Transaction.statement_account_id.is_(None))
        .group_by(Transaction.currency)
        .order_by(Transaction.currency)
    ).all()
    return UnlinkedSummary(count, list(banks), earliest, latest, [(currency, Decimal(net)) for currency, net in nets])


def nearest_earlier_rate(db: Session, currency: str, on_or_before: date) -> tuple[Decimal, date] | None:
    """The cached rate for `currency` to SGD dated on or before the date, the nearest such date; None if there is
    none. Cache-only: never an external call (AR-59, Application Design Question 1 = A)."""
    row = db.execute(
        select(FxRateCache.rate, FxRateCache.rate_date)
        .where(
            FxRateCache.from_currency == currency,
            FxRateCache.to_currency == "SGD",
            FxRateCache.rate_date <= on_or_before,
        )
        .order_by(FxRateCache.rate_date.desc())
        .limit(1)
    ).first()
    return (Decimal(row[0]), row[1]) if row else None
