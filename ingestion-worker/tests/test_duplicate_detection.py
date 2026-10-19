from datetime import date
from decimal import Decimal

import pytest
from transactagent_db.models import (
    Account,
    DuplicateComparison,
    KnownFile,
    KnownFileState,
    StatementAccount,
)

from ingestion_worker.accounts.service import ResolvedSection
from ingestion_worker.duplicate_detection import service
from ingestion_worker.extraction.schemas import RawAccountSection


class TestComputeFileHash:
    def test_same_bytes_produce_same_hash(self):
        assert service.compute_file_hash(b"hello world") == service.compute_file_hash(b"hello world")

    def test_different_bytes_produce_different_hash(self):
        assert service.compute_file_hash(b"hello") != service.compute_file_hash(b"world")

    def test_hash_is_sha256_hex_digest(self):
        result = service.compute_file_hash(b"test")
        assert len(result) == 64
        int(result, 16)  # raises if not valid hex


class TestFindAndRecordProcessed:
    def test_new_hash_is_not_found(self, db_session):
        assert service.find_existing_statement(db_session, "a" * 64) is None

    def test_recorded_statement_is_then_found(self, db_session):
        service.record_processed(db_session, drive_file_id="f1", pdf_content_hash="b" * 64, bank_name="DBS")
        found = service.find_existing_statement(db_session, "b" * 64)
        assert found is not None
        assert found.bank_name == "DBS"


class TestRecordStatementAccounts:
    """Epic 13 (WR-51): one StatementAccount per resolved account section."""

    def _resolved(self, db, name, **section_fields):
        account = Account(name=name, bank_name="DBS", currency="SGD")
        db.add(account)
        db.flush()
        return ResolvedSection(section=RawAccountSection(currency="SGD", **section_fields), account=account, was_created=True)

    def test_one_row_per_section_in_order_with_the_closing_balance(self, db_session):
        statement = service.record_processed(db_session, drive_file_id="f", pdf_content_hash="c" * 64, bank_name="DBS")
        first = self._resolved(db_session, "Savings", closing_balance=Decimal("100.25"), closing_balance_date=date(2026, 1, 31))
        second = self._resolved(db_session, "Card")

        rows = service.record_statement_accounts(db_session, statement, [first, second])

        assert [r.account_id for r in rows] == [first.account.id, second.account.id]
        assert rows[0].closing_balance == Decimal("100.25") and rows[0].closing_balance_date == date(2026, 1, 31)
        assert rows[1].closing_balance is None and rows[1].closing_balance_date is None
        assert db_session.query(StatementAccount).filter_by(bank_statement_id=statement.id).count() == 2

    def test_a_statement_with_no_sections_records_none(self, db_session):
        statement = service.record_processed(db_session, drive_file_id="f", pdf_content_hash="d" * 64, bank_name="DBS")

        assert service.record_statement_accounts(db_session, statement, []) == []


class TestLookupRememberedFile:
    """Epic 14 (WR-61): the remembered decision for a file's content, found before extraction."""

    def _comparison(self, db):
        comparison = DuplicateComparison(
            earlier_content_hash="e" * 64, earlier_period_start=date(2026, 6, 2), earlier_period_end=date(2026, 6, 30),
            earlier_transaction_count=5, later_content_hash="f" * 64, later_period_start=date(2026, 6, 2),
            later_period_end=date(2026, 6, 30), later_transaction_count=5, matched_count=5,
            match_ratio=Decimal("1.0000"), reason="5 of 5 transactions match",
        )
        db.add(comparison)
        db.flush()
        return comparison

    def test_an_unknown_hash_has_no_record(self, db_session):
        assert service.lookup_remembered_file(db_session, "9" * 64) is None

    @pytest.mark.parametrize("state", list(KnownFileState))
    def test_each_state_is_found_with_its_evidence(self, db_session, state):
        comparison = self._comparison(db_session)
        db_session.add(KnownFile(pdf_content_hash="f" * 64, state=state, matched_statement_hash="e" * 64, comparison_id=comparison.id))
        db_session.flush()

        found = service.lookup_remembered_file(db_session, "f" * 64)

        assert found.state is state
        assert found.matched_statement_hash == "e" * 64 and found.comparison_id == comparison.id

    def test_the_exact_bytes_check_is_unaffected(self, db_session):
        """NFR-PD-6: a remembered record does not make find_existing_statement find anything."""
        comparison = self._comparison(db_session)
        db_session.add(KnownFile(pdf_content_hash="f" * 64, state=KnownFileState.PROBABLE_DUPLICATE, matched_statement_hash="e" * 64, comparison_id=comparison.id))
        db_session.flush()

        assert service.find_existing_statement(db_session, "f" * 64) is None

