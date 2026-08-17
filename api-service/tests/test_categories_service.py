from datetime import date
from decimal import Decimal

import pytest
from transactagent_db.models import BankStatement, CategorySource, Transaction

from api_service.categories import service
from api_service.errors import (
    CategoryInUseError,
    DuplicateCategoryNameError,
    ReservedCategoryError,
)


def _make_bank_statement(db, pdf_content_hash="a" * 64):
    stmt = BankStatement(drive_file_id="f1", pdf_content_hash=pdf_content_hash)
    db.add(stmt)
    db.flush()
    return stmt


class TestAddCategory:
    def test_add_new_category_succeeds(self, db_session):
        category = service.add_category(db_session, "Groceries")
        assert category.name == "Groceries"
        assert category.active is True

    def test_add_duplicate_name_is_rejected(self, db_session):
        service.add_category(db_session, "Dining")
        with pytest.raises(DuplicateCategoryNameError):
            service.add_category(db_session, "Dining")


class TestRenameCategory:
    def test_rename_reserved_category_is_rejected(self, db_session):
        unsure = service.add_category(db_session, "UNSURE")
        unsure.is_reserved = True
        db_session.flush()
        with pytest.raises(ReservedCategoryError):
            service.rename_category(db_session, unsure.id, "Not Sure")

    def test_rename_to_existing_name_is_rejected(self, db_session):
        service.add_category(db_session, "Bills")
        target = service.add_category(db_session, "Utilities")
        with pytest.raises(DuplicateCategoryNameError):
            service.rename_category(db_session, target.id, "Bills")


class TestRemoveCategory:
    def test_remove_unused_category_succeeds(self, db_session):
        category = service.add_category(db_session, "Pets")
        service.remove_category(db_session, category.id)
        db_session.refresh(category)
        assert category.active is False

    def test_remove_category_in_use_is_rejected(self, db_session):
        category = service.add_category(db_session, "Transport")
        statement = _make_bank_statement(db_session)
        txn = Transaction(
            bank_statement_id=statement.id,
            transaction_date=date(2026, 1, 1),
            description="Grab ride",
            out_flow=Decimal("15.00"),
            currency="SGD",
            bank_name="DBS",
            category_id=category.id,
            category_source=CategorySource.MANUAL,
        )
        db_session.add(txn)
        db_session.flush()

        with pytest.raises(CategoryInUseError) as exc_info:
            service.remove_category(db_session, category.id)
        assert exc_info.value.details["blockedByTransactionCount"] == 1

    def test_remove_reserved_category_is_rejected(self, db_session):
        unsure = service.add_category(db_session, "UNSURE-2")
        unsure.is_reserved = True
        db_session.flush()
        with pytest.raises(ReservedCategoryError):
            service.remove_category(db_session, unsure.id)
