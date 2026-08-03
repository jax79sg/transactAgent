from datetime import date
from decimal import Decimal

import pytest

from api_service.categories import service as categories_service
from api_service.errors import CategoryNotFoundError, InactiveCategoryError, InvalidCurrencyError
from api_service.transactions import service as transactions_service
from api_service.transactions.schemas import TransactionListQuery
from transactagent_db.models import BankStatement, CategorySource, RecategorizationJobStatus, Transaction


def _make_transaction(db, category, description="NTUC FAIRPRICE"):
    statement = BankStatement(drive_file_id="f-x", pdf_content_hash="c" * 64)
    db.add(statement)
    db.flush()
    txn = Transaction(
        bank_statement_id=statement.id,
        transaction_date=date(2026, 1, 10),
        description=description,
        out_flow=Decimal("42.00"),
        currency="SGD",
        bank_name="DBS",
        category_id=category.id,
        category_source=CategorySource.SIMILARITY,
    )
    db.add(txn)
    db.flush()
    return txn


class TestCorrectTransactionCategory:
    def test_successful_correction_creates_recategorization_job(self, db_session):
        old_category = categories_service.add_category(db_session, "Others")
        new_category = categories_service.add_category(db_session, "Groceries")
        txn = _make_transaction(db_session, old_category)

        updated_txn, job = transactions_service.correct_transaction_category(db_session, txn.id, new_category.id)

        assert updated_txn.category_id == new_category.id
        assert updated_txn.category_source == CategorySource.MANUAL
        assert job.source_transaction_id == txn.id
        assert job.status == RecategorizationJobStatus.QUEUED

    def test_correction_to_inactive_category_is_rejected(self, db_session):
        category = categories_service.add_category(db_session, "Old Category")
        txn = _make_transaction(db_session, category)
        inactive_category = categories_service.add_category(db_session, "Retired")
        categories_service.remove_category(db_session, inactive_category.id)

        with pytest.raises(InactiveCategoryError):
            transactions_service.correct_transaction_category(db_session, txn.id, inactive_category.id)

    def test_correction_to_unknown_category_is_rejected(self, db_session):
        category = categories_service.add_category(db_session, "Known")
        txn = _make_transaction(db_session, category)
        import uuid

        with pytest.raises(CategoryNotFoundError):
            transactions_service.correct_transaction_category(db_session, txn.id, uuid.uuid4())

    def test_correcting_unknown_transaction_is_rejected(self, db_session):
        category = categories_service.add_category(db_session, "Any")
        import uuid

        with pytest.raises(CategoryNotFoundError):
            transactions_service.correct_transaction_category(db_session, uuid.uuid4(), category.id)


class TestListTransactionsCurrencyValidation:
    def test_invalid_currency_filter_is_rejected(self, db_session):
        query = TransactionListQuery(currency="not-a-code")
        with pytest.raises(InvalidCurrencyError):
            transactions_service.list_transactions(db_session, query)

    def test_valid_currency_filter_is_accepted(self, db_session):
        category = categories_service.add_category(db_session, "Dining Out")
        _make_transaction(db_session, category)
        query = TransactionListQuery(currency="SGD")
        items, total_count, groups = transactions_service.list_transactions(db_session, query)
        assert total_count >= 1
