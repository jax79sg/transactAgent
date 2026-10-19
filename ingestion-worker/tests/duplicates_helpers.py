"""Builders for the probable-duplicate tests: held statements (with transactions, sections and
run files) and extracted statements, using the real models."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from transactagent_db.models import (
    Account,
    AccountKey,
    AccountType,
    BankStatement,
    Category,
    CategorySource,
    IngestionRun,
    IngestionRunFile,
    IngestionRunFileOutcome,
    IngestionRunStatus,
    StatementAccount,
    Transaction,
    User,
)

from ingestion_worker.accounts.normalize import bank_key
from ingestion_worker.extraction.schemas import (
    ConfidenceLevel,
    Direction,
    RawAccountSection,
    RawExtractedStatement,
    RawExtractedTransaction,
)

BASE_TIME = datetime(2026, 8, 4, 9, 0, tzinfo=UTC)


def june(n, *, month=6, prefix="MERCHANT"):
    """n distinct (day, amount, description) rows spread over a month."""
    return [(date(2026, month, 2 + i), f"{10 + i}.00", f"{prefix} {i}") for i in range(n)]


def ensure_category(db, name="Groceries"):
    category = db.query(Category).filter_by(name=name).first()
    if category is None:
        category = Category(name=name, active=True, is_reserved=(name == "UNSURE"))
        db.add(category)
        db.flush()
    return category


def ensure_run(db):
    run = db.query(IngestionRun).first()
    if run is None:
        user = User(username=f"owner-{uuid.uuid4().hex[:6]}", password_hash="x")
        db.add(user)
        db.flush()
        run = IngestionRun(triggered_by_user_id=user.id, status=IngestionRunStatus.COMPLETED)
        db.add(run)
        db.flush()
    return run


def make_statement(
    db,
    *,
    h,
    bank="UOB",
    rows=None,
    ingested_days=0,
    file_name=None,
    manual=0,
    accounts=(),  # (identifier, currency, closing_balance|None, closing_date|None)
    direction="out",
):
    """A held statement. `manual` makes that many of its transactions manual corrections."""
    statement = BankStatement(
        drive_file_id=f"drive-{h[:6]}",
        pdf_content_hash=h,
        bank_name=bank,
        processed_at=BASE_TIME + timedelta(days=ingested_days),
    )
    db.add(statement)
    db.flush()
    category = ensure_category(db)
    sections = []
    for identifier, currency, balance, balance_date in accounts:
        account = Account(name=f"{bank} {identifier}", bank_name=bank, account_type=AccountType.DEPOSIT, currency=currency)
        db.add(account)
        db.flush()
        db.add(AccountKey(account_id=account.id, bank_key=bank_key(bank), account_identifier=identifier, currency=currency))
        sections.append(
            StatementAccount(bank_statement_id=statement.id, account_id=account.id, closing_balance=balance, closing_balance_date=balance_date)
        )
    db.add_all(sections)
    db.flush()
    for index, (day, amount, description) in enumerate(rows or []):
        db.add(
            Transaction(
                bank_statement_id=statement.id,
                statement_account_id=sections[0].id if sections else None,
                transaction_date=day,
                description=description,
                out_flow=Decimal(amount) if direction == "out" else None,
                in_flow=Decimal(amount) if direction == "in" else None,
                currency=accounts[0][1] if accounts else "SGD",
                bank_name=bank,
                category_id=category.id,
                category_source=CategorySource.MANUAL if index < manual else CategorySource.SIMILARITY,
            )
        )
    if file_name:
        run = ensure_run(db)
        db.add(
            IngestionRunFile(
                ingestion_run_id=run.id,
                drive_file_id=statement.drive_file_id,
                drive_file_name=file_name,
                outcome=IngestionRunFileOutcome.PROCESSED,
                bank_statement_id=statement.id,
            )
        )
    db.flush()
    return statement


def extracted(rows, *, bank="UOB", currency="SGD", identifier=None, closing=None, direction="out"):
    """An extracted statement with one section. `closing` is (balance, date) or None."""
    transactions = [
        RawExtractedTransaction(
            transaction_date=day,
            description=description,
            amount=Decimal(amount),
            direction=Direction(direction),
            confidence=ConfidenceLevel.HIGH,
        )
        for day, amount, description in rows
    ]
    section = RawAccountSection(
        account_identifier=identifier,
        currency=currency,
        closing_balance=Decimal(closing[0]) if closing else None,
        closing_balance_date=closing[1] if closing else None,
        transactions=transactions,
    )
    return RawExtractedStatement(bank_name=bank, currency=currency, confidence=ConfidenceLevel.HIGH, sections=[section])
