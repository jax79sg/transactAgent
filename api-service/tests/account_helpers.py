"""Builders for accounts, statements, sections and transactions, shared by the Epic 13 tests."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from transactagent_db.models import (
    Account,
    AccountKey,
    AccountType,
    BalanceAnchor,
    BankStatement,
    Category,
    CategorySource,
    FxRateCache,
    StatementAccount,
    Transaction,
)

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def category(db, name="Others"):
    existing = db.query(Category).filter_by(name=name).one_or_none()
    if existing:
        return existing
    created = Category(name=name, active=True, is_reserved=False)
    db.add(created)
    db.flush()
    return created


def make_account(db, name="DBS 1234", account_type=AccountType.DEPOSIT, currency="SGD", bank="DBS", identifier="1234", user_set=False):
    account = Account(name=name, bank_name=bank, account_type=account_type, currency=currency, type_user_set=user_set)
    db.add(account)
    db.flush()
    db.add(AccountKey(account_id=account.id, bank_key=bank.lower(), account_identifier=identifier, currency=currency))
    db.flush()
    return account


def make_statement(db, bank="DBS"):
    statement = BankStatement(drive_file_id="f-" + uuid.uuid4().hex[:8], pdf_content_hash=uuid.uuid4().hex + uuid.uuid4().hex[:32], bank_name=bank)
    db.add(statement)
    db.flush()
    return statement


_section_count = 0


def make_section(db, account, statement=None, closing=None, closing_date=None):
    """A statement-account row; `created_at` is set explicitly and increasing so record order is deterministic."""
    global _section_count
    _section_count += 1
    statement = statement or make_statement(db, account.bank_name)
    section = StatementAccount(
        bank_statement_id=statement.id,
        account_id=account.id,
        closing_balance=Decimal(closing) if closing is not None else None,
        closing_balance_date=closing_date,
        created_at=_EPOCH + timedelta(seconds=_section_count),
    )
    db.add(section)
    db.flush()
    return section


def make_tx(db, section, day, amount, currency="SGD", description="a transaction", bank=None):
    """A transaction on a section; `amount` is signed: positive is an inflow, negative an outflow."""
    value = Decimal(amount)
    txn = Transaction(
        bank_statement_id=section.bank_statement_id,
        statement_account_id=section.id,
        transaction_date=day,
        description=description,
        in_flow=value if value > 0 else None,
        out_flow=-value if value < 0 else None,
        currency=currency,
        bank_name=bank or "DBS",
        category_id=category(db).id,
        category_source=CategorySource.MANUAL,
    )
    db.add(txn)
    db.flush()
    return txn


def make_unlinked_tx(db, day, amount, bank="GXS Bank", currency="SGD"):
    statement = make_statement(db, bank)
    value = Decimal(amount)
    txn = Transaction(
        bank_statement_id=statement.id,
        statement_account_id=None,
        transaction_date=day,
        description="unlinked",
        in_flow=value if value > 0 else None,
        out_flow=-value if value < 0 else None,
        currency=currency,
        bank_name=bank,
        category_id=category(db).id,
        category_source=CategorySource.MANUAL,
    )
    db.add(txn)
    db.flush()
    return txn


def set_anchor(db, account, balance, day):
    anchor = BalanceAnchor(account_id=account.id, balance=Decimal(balance), as_of_date=day)
    db.add(anchor)
    db.flush()
    return anchor


def make_fx_rate(db, currency, day, rate):
    row = FxRateCache(from_currency=currency, to_currency="SGD", rate_date=day, rate=Decimal(rate))
    db.add(row)
    db.flush()
    return row


def account_with_history(db, name="DBS 1234", anchor=None, flows=(), **kwargs):
    """A deposit account with one statement section and the given (date, amount) transactions; optionally an anchor
    given as (balance, date)."""
    account = make_account(db, name=name, **kwargs)
    section = make_section(db, account)
    for day, amount in flows:
        make_tx(db, section, day, amount)
    if anchor:
        set_anchor(db, account, anchor[0], anchor[1])
    return account, section
