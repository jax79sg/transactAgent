"""Transaction query/filter/group and manual-correction business logic.

Implements business-logic-model.md's Transaction Management Component: AR-2 (inactive
category rejected), AR-7 (unrecognized category rejected), AR-8 (pagination bounds),
AR-9 (currency validation), AR-10 (recategorization job only on manual correction).
"""

import csv
import io
import re
from uuid import UUID

from sqlalchemy.orm import Session
from transactagent_db.models import CategorySource, RecategorizationJob, Transaction

from api_service.categories import repository as categories_repository
from api_service.config import settings
from api_service.errors import (
    CategoryNotFoundError,
    InactiveCategoryError,
    InvalidCurrencyError,
)
from api_service.transactions import repository
from api_service.transactions.schemas import TransactionFilter, TransactionListQuery

_ISO4217_PATTERN = re.compile(r"^[A-Z]{3}$")


def _validate_currency(currency: str | None) -> None:
    if currency is not None and not _ISO4217_PATTERN.match(currency):
        raise InvalidCurrencyError(f"'{currency}' is not a valid ISO 4217 currency code")


def list_transactions(db: Session, query: TransactionListQuery) -> tuple[list[Transaction], int, list[dict]]:
    _validate_currency(query.currency)
    page_size = min(query.page_size, settings.max_page_size)
    items, total_count = repository.query_transactions(db, query, page=query.page, page_size=page_size)
    groups: list[dict] = []
    if query.group_by is not None:
        groups = repository.query_group_summaries(db, query)
    return items, total_count, groups


def list_distinct_banks(db: Session) -> list[str]:
    return repository.list_distinct_banks(db)


def export_transactions_csv(db: Session, filters: TransactionFilter) -> str:
    _validate_currency(filters.currency)
    rows = repository.query_all_for_export(db, filters, max_rows=settings.csv_export_max_rows)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Transaction Date",
            "Transaction Description",
            "Out-flow",
            "In-flow",
            "Bank name",
            "Transaction Category",
            "Currency",
            "Converted Amount (SGD)",
        ]
    )
    for txn in rows:
        writer.writerow(
            [
                txn.transaction_date.isoformat(),
                txn.description,
                txn.out_flow if txn.out_flow is not None else "",
                txn.in_flow if txn.in_flow is not None else "",
                txn.bank_name,
                txn.category.name,
                txn.currency,
                txn.converted_amount_sgd if txn.converted_amount_sgd is not None else "",
            ]
        )
    return buffer.getvalue()


def correct_transaction_category(db: Session, transaction_id: UUID, new_category_id: UUID) -> tuple[Transaction, RecategorizationJob]:
    transaction = repository.find_by_id(db, transaction_id)
    if transaction is None:
        raise CategoryNotFoundError(f"Transaction {transaction_id} not found")

    category = categories_repository.find_by_id(db, new_category_id)
    if category is None:
        raise CategoryNotFoundError(f"Category {new_category_id} not found")
    if not category.active:
        raise InactiveCategoryError(f"Category '{category.name}' is inactive and cannot be assigned")

    transaction.category_id = category.id
    transaction.category_source = CategorySource.MANUAL
    db.flush()

    # AR-10: a RecategorizationJob is created if and only if this correction results
    # in category_source = 'manual' -- which is always true for this code path, since
    # this function is the only place transactions are manually corrected.
    job = repository.create_recategorization_job(db, source_transaction_id=transaction.id)

    return transaction, job
