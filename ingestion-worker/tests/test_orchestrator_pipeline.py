"""Integration-style tests for the orchestrator pipeline: real Postgres (testcontainers),
external clients (Drive, Gemini, OpenRouter, FX) mocked at their client-module boundary.
"""

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

from transactagent_db.models import (
    Account,
    AccountType,
    BankStatement,
    Category,
    IngestionRun,
    IngestionRunFile,
    IngestionRunFileOutcome,
    IngestionRunStatus,
    StatementAccount,
    Transaction,
    User,
)

from ingestion_worker.clients.drive_client import DriveFileRef
from ingestion_worker.orchestrator import pipeline

_VALID_EXTRACTION_RESPONSE = json.dumps(
    {
        "bank_name": "DBS",
        "currency": "SGD",
        "confidence": "high",
        "transactions": [
            {
                "transaction_date": "2026-01-15",
                "description": "NTUC FAIRPRICE",
                "amount": 25.50,
                "direction": "out",
                "printed_converted_amount_sgd": None,
                "confidence": "high",
            }
        ],
    }
)


def _make_run(db):
    # A fresh username per call -- users.username is unique, and a test creating two
    # runs (e.g. to exercise duplicate-detection across separate runs) would otherwise
    # collide on the second _make_run() call (caught by actually running this).
    user = User(username=f"account_owner-{uuid.uuid4()}", password_hash="hashed")
    db.add(user)
    db.flush()
    run = IngestionRun(triggered_by_user_id=user.id, status=IngestionRunStatus.RUNNING)
    db.add(run)
    db.flush()
    return run


def _seed_whitelist(db):
    for name in ["Groceries", "UNSURE"]:
        db.add(Category(name=name, active=True, is_reserved=(name == "UNSURE")))
    db.flush()


class TestProcessRunHappyPath:
    def test_single_new_file_is_processed_and_persisted(self, db_session):
        _seed_whitelist(db_session)
        run = _make_run(db_session)
        file_ref = DriveFileRef(id="drive-1", name="statement.pdf")

        with (
            patch("ingestion_worker.clients.drive_client.list_folder_pdf_files", return_value=[file_ref]),
            patch("ingestion_worker.clients.drive_client.download_file", return_value=b"fake-pdf-bytes"),
            patch(
                "ingestion_worker.extraction.service._pdf_to_page_images", return_value=[b"fake-page-bytes"]
            ),
            patch(
                "ingestion_worker.extraction.service.extract_statement_raw",
                return_value=_VALID_EXTRACTION_RESPONSE,
            ),
            patch("ingestion_worker.clients.openrouter_client.classify_description", return_value="Groceries"),
        ):
            pipeline.process_run(db_session, run)

        db_session.refresh(run)
        assert run.status == IngestionRunStatus.COMPLETED
        assert run.files_found_count == 1
        assert run.files_processed_count == 1
        assert run.files_failed_count == 0

        transactions = db_session.query(Transaction).all()
        assert len(transactions) == 1
        assert transactions[0].description == "NTUC FAIRPRICE"
        assert transactions[0].category.name in ("Groceries", "UNSURE")  # similarity->none, LLM fallback used
        assert transactions[0].converted_amount_sgd == transactions[0].out_flow  # SGD identity conversion

    def test_duplicate_file_is_skipped_no_new_transactions(self, db_session):
        _seed_whitelist(db_session)
        run = _make_run(db_session)
        file_ref = DriveFileRef(id="drive-2", name="statement.pdf")

        with (
            patch("ingestion_worker.clients.drive_client.list_folder_pdf_files", return_value=[file_ref]),
            patch("ingestion_worker.clients.drive_client.download_file", return_value=b"fake-pdf-bytes"),
            patch(
                "ingestion_worker.extraction.service._pdf_to_page_images", return_value=[b"fake-page-bytes"]
            ),
            patch(
                "ingestion_worker.extraction.service.extract_statement_raw",
                return_value=_VALID_EXTRACTION_RESPONSE,
            ),
            patch("ingestion_worker.clients.openrouter_client.classify_description", return_value="Groceries"),
        ):
            pipeline.process_run(db_session, run)

        run2 = _make_run(db_session)
        with (
            patch("ingestion_worker.clients.drive_client.list_folder_pdf_files", return_value=[file_ref]),
            patch("ingestion_worker.clients.drive_client.download_file", return_value=b"fake-pdf-bytes"),
        ):
            pipeline.process_run(db_session, run2)

        db_session.refresh(run2)
        assert run2.files_skipped_count == 1
        assert run2.files_processed_count == 0
        assert db_session.query(Transaction).count() == 1  # still just the first run's transaction

    def test_one_file_failure_does_not_abort_the_run(self, db_session):
        """NFR-2.2: partial-failure isolation."""
        _seed_whitelist(db_session)
        run = _make_run(db_session)
        good_file = DriveFileRef(id="drive-good", name="good.pdf")
        bad_file = DriveFileRef(id="drive-bad", name="bad.pdf")

        call_count = {"n": 0}

        def fake_download(db, file_ref):
            call_count["n"] += 1
            return b"fake-pdf-bytes-" + str(call_count["n"]).encode()

        with (
            patch(
                "ingestion_worker.clients.drive_client.list_folder_pdf_files",
                return_value=[bad_file, good_file],
            ),
            patch("ingestion_worker.clients.drive_client.download_file", side_effect=fake_download),
            patch("ingestion_worker.extraction.service._pdf_to_page_images", return_value=[b"page"]),
            patch(
                "ingestion_worker.extraction.service.extract_statement_raw",
                side_effect=["not valid json", _VALID_EXTRACTION_RESPONSE],
            ),
            patch("ingestion_worker.clients.openrouter_client.classify_description", return_value="Groceries"),
        ):
            pipeline.process_run(db_session, run)

        db_session.refresh(run)
        assert run.status == IngestionRunStatus.COMPLETED_WITH_FAILURES
        assert run.files_failed_count == 1
        assert run.files_processed_count == 1

        files = db_session.query(IngestionRunFile).filter_by(ingestion_run_id=run.id).all()
        outcomes = {f.drive_file_id: f.outcome for f in files}
        assert outcomes["drive-bad"] == IngestionRunFileOutcome.FAILED
        assert outcomes["drive-good"] == IngestionRunFileOutcome.PROCESSED


class TestProcessRunLiveProgressVisibility:
    """Regression: previously repository.update_run_progress/complete_run/fail_run only
    called db.flush(), and the whole run ran inside one long-lived session that
    committed just once at the very end (main.py's single session_scope() wrapping the
    entire process_run() call) -- so a concurrent reader (the API service, a separate
    process/connection entirely) saw status='running', files_found=0 for the run's
    entire duration. Caught by a user watching the frontend's live-progress UI and
    seeing no movement at all (aidlc-docs/audit.md).

    This verifies the fix at the level that actually matters for production --
    db.commit() calls, which are what make data visible to other connections --
    without needing a second real DB connection: the db_session fixture deliberately
    wraps every test in an outer, never-committed transaction so tests roll back
    cleanly, which means even a real commit() from application code stays invisible to
    any other connection for the lifetime of this fixture. That's correct for test
    isolation, but it also means a cross-connection-visibility test can't be built on
    top of this fixture -- so we assert on commit() call count instead."""

    def test_progress_commits_incrementally_not_only_at_run_completion(self, db_session):
        _seed_whitelist(db_session)
        run = _make_run(db_session)
        file_ref = DriveFileRef(id="drive-visible", name="statement.pdf")

        commit_count = {"n": 0}
        real_commit = db_session.commit

        def counting_commit():
            commit_count["n"] += 1
            real_commit()

        with (
            patch.object(db_session, "commit", side_effect=counting_commit),
            patch("ingestion_worker.clients.drive_client.list_folder_pdf_files", return_value=[file_ref]),
            patch("ingestion_worker.clients.drive_client.download_file", return_value=b"fake-pdf-bytes"),
            patch(
                "ingestion_worker.extraction.service._pdf_to_page_images", return_value=[b"fake-page-bytes"]
            ),
            patch(
                "ingestion_worker.extraction.service.extract_statement_raw",
                return_value=_VALID_EXTRACTION_RESPONSE,
            ),
            patch("ingestion_worker.clients.openrouter_client.classify_description", return_value="Groceries"),
        ):
            pipeline.process_run(db_session, run)

        # files_found update, the per-file processed update, and complete_run each
        # commit separately -- proving progress persists incrementally rather than in
        # one final commit at the end of the run.
        assert commit_count["n"] >= 3


class TestProcessRunLogAttribution:
    """The live log-tail view attributes captured log lines to a run via a module-level
    "current run" value (logging_capture.set_current_run) rather than passing the run
    id through every function call -- this verifies it's set for the run's duration and
    always cleared afterward, on every exit path (success, listing failure, per-file
    failure), so log lines from the *next* run (or idle poll-cycle chatter) never get
    misattributed to a finished one."""

    def test_run_id_is_set_during_and_cleared_after_a_successful_run(self, db_session):
        from ingestion_worker import logging_capture

        _seed_whitelist(db_session)
        run = _make_run(db_session)
        file_ref = DriveFileRef(id="drive-log-attr", name="statement.pdf")
        seen_during_run = {}

        def spying_list_files(db):
            seen_during_run["run_id"] = logging_capture._current_run_id
            return [file_ref]

        with (
            patch("ingestion_worker.clients.drive_client.list_folder_pdf_files", side_effect=spying_list_files),
            patch("ingestion_worker.clients.drive_client.download_file", return_value=b"fake-pdf-bytes"),
            patch("ingestion_worker.extraction.service._pdf_to_page_images", return_value=[b"fake-page-bytes"]),
            patch(
                "ingestion_worker.extraction.service.extract_statement_raw",
                return_value=_VALID_EXTRACTION_RESPONSE,
            ),
            patch("ingestion_worker.clients.openrouter_client.classify_description", return_value="Groceries"),
        ):
            pipeline.process_run(db_session, run)

        assert seen_during_run["run_id"] == str(run.id)
        assert logging_capture._current_run_id is None

    def test_run_id_is_cleared_even_when_the_run_fails(self, db_session):
        from ingestion_worker import logging_capture

        _seed_whitelist(db_session)
        run = _make_run(db_session)

        with patch(
            "ingestion_worker.clients.drive_client.list_folder_pdf_files",
            side_effect=RuntimeError("simulated failure"),
        ):
            pipeline.process_run(db_session, run)

        assert logging_capture._current_run_id is None


class TestProcessRunCancellation:
    """User-initiated cancellation (2026-08-05, see aidlc-docs/audit.md): checked
    between files, never mid-file, so a file already being processed always
    finishes and gets recorded -- only files not yet started are skipped. Real
    IngestionRun.cancel_requested_at is written only by the API in production; here
    it's set directly on the row (same effect a committed cross-process write would
    have, since the pipeline's is_cancellation_requested() does a fresh query)."""

    def test_cancellation_requested_mid_run_stops_before_next_file(self, db_session):
        _seed_whitelist(db_session)
        run = _make_run(db_session)
        file1 = DriveFileRef(id="drive-cancel-1", name="file1.pdf")
        file2 = DriveFileRef(id="drive-cancel-2", name="file2.pdf")

        def fake_download(db, file_ref):
            return b"fake-pdf-bytes-" + file_ref.id.encode()

        def classify_and_request_cancellation(description, amount_sgd, whitelist, model=None):
            # Simulates the API committing cancel_requested_at while file1 (the
            # only file with a transaction to classify) is still being processed --
            # file1 must still finish and be recorded; only file2 gets skipped.
            run.cancel_requested_at = datetime.now(UTC)
            db_session.commit()
            return "Groceries"

        with (
            patch(
                "ingestion_worker.clients.drive_client.list_folder_pdf_files", return_value=[file1, file2]
            ),
            patch("ingestion_worker.clients.drive_client.download_file", side_effect=fake_download),
            patch("ingestion_worker.extraction.service._pdf_to_page_images", return_value=[b"page"]),
            patch(
                "ingestion_worker.extraction.service.extract_statement_raw",
                return_value=_VALID_EXTRACTION_RESPONSE,
            ),
            # Patched where llm_classifier looks it up (its own `from ... import
            # classify_description` binding), not where it's defined -- patching
            # clients.openrouter_client.classify_description alone would leave
            # llm_classifier's already-bound reference untouched, so this side
            # effect would silently never run (the real function would, and fail
            # closed to UNSURE -- see categorization/llm_classifier.py's catch-all).
            patch(
                "ingestion_worker.categorization.llm_classifier.classify_description",
                side_effect=classify_and_request_cancellation,
            ),
        ):
            pipeline.process_run(db_session, run)

        db_session.refresh(run)
        assert run.status == IngestionRunStatus.CANCELLED
        assert run.completed_at is not None
        assert run.files_found_count == 2
        assert run.files_processed_count == 1  # file1 finished before the checkpoint saw cancellation

        # file1's data is durable -- cancellation never rolls back already-committed work.
        transactions = db_session.query(Transaction).all()
        assert len(transactions) == 1
        assert transactions[0].description == "NTUC FAIRPRICE"

        files = db_session.query(IngestionRunFile).filter_by(ingestion_run_id=run.id).all()
        assert len(files) == 1  # file2 was never attempted, so it has no run-file record at all
        assert files[0].drive_file_id == "drive-cancel-1"

    def test_cancellation_requested_before_any_file_processes_nothing(self, db_session):
        _seed_whitelist(db_session)
        run = _make_run(db_session)
        run.cancel_requested_at = datetime.now(UTC)
        db_session.commit()
        file_ref = DriveFileRef(id="drive-cancel-early", name="never-touched.pdf")

        with patch(
            "ingestion_worker.clients.drive_client.list_folder_pdf_files", return_value=[file_ref]
        ) as mock_list, patch("ingestion_worker.clients.drive_client.download_file") as mock_download:
            pipeline.process_run(db_session, run)

        db_session.refresh(run)
        assert run.status == IngestionRunStatus.CANCELLED
        mock_list.assert_called_once()  # listing still happens (cheap, needed for files_found_count)
        mock_download.assert_not_called()  # but no file is ever downloaded/processed
        assert db_session.query(Transaction).count() == 0

    def test_cancelling_a_run_frees_the_single_active_run_slot_for_a_new_one(self, db_session):
        _seed_whitelist(db_session)
        run = _make_run(db_session)
        run.cancel_requested_at = datetime.now(UTC)
        db_session.commit()

        with patch("ingestion_worker.clients.drive_client.list_folder_pdf_files", return_value=[]):
            pipeline.process_run(db_session, run)

        # The whole point of reaching a real terminal status immediately: the next
        # run must not be blocked by ingestion_runs' single-active-run constraint.
        new_run = IngestionRun(triggered_by_user_id=run.triggered_by_user_id, status=IngestionRunStatus.QUEUED)
        db_session.add(new_run)
        db_session.flush()  # would raise IntegrityError if the cancelled row still counted as active


class TestProcessRunUnexpectedErrors:
    """Regression coverage: a run must never be left stuck in RUNNING, since
    ingestion_runs' single-active-run unique constraint would then block every future
    run. Previously only DriveNotConnectedError/DriveReauthRequiredError/TransientError
    were caught -- a real googleapiclient.errors.HttpError (Drive API disabled on the
    Google Cloud project) fell through uncaught and orphaned the run (aidlc-docs/audit.md)."""

    def test_unexpected_error_during_listing_still_fails_run(self, db_session):
        _seed_whitelist(db_session)
        run = _make_run(db_session)

        with patch(
            "ingestion_worker.clients.drive_client.list_folder_pdf_files",
            side_effect=RuntimeError("simulated raw googleapiclient HttpError"),
        ):
            pipeline.process_run(db_session, run)

        db_session.refresh(run)
        assert run.status == IngestionRunStatus.FAILED

    def test_unexpected_error_during_file_processing_still_fails_run(self, db_session):
        _seed_whitelist(db_session)
        run = _make_run(db_session)
        file_ref = DriveFileRef(id="drive-3", name="statement.pdf")

        with (
            patch("ingestion_worker.clients.drive_client.list_folder_pdf_files", return_value=[file_ref]),
            patch(
                "ingestion_worker.clients.drive_client.download_file",
                side_effect=RuntimeError("simulated unexpected bug"),
            ),
        ):
            pipeline.process_run(db_session, run)

        db_session.refresh(run)
        assert run.status == IngestionRunStatus.FAILED


def _txn_json(description, day="2026-01-15", amount=25.5, printed_sgd=None):
    return {
        "transaction_date": day, "description": description, "amount": amount, "direction": "out",
        "printed_converted_amount_sgd": printed_sgd, "confidence": "high",
    }


def _sectioned_response(*sections, bank="OCBC Bank", currency="SGD"):
    return json.dumps({"bank_name": bank, "currency": currency, "confidence": "high", "sections": list(sections)})


def _ingest(db_session, files, responses, *, classify=None):
    """Run the pipeline over `files` with one extraction response per file (different PDF bytes
    each, so duplicate detection treats them as distinct statements)."""
    run = _make_run(db_session)
    counter = {"n": 0}

    def fake_download(db, file_ref):
        counter["n"] += 1
        return b"pdf-bytes-" + str(counter["n"]).encode()

    classify = classify or (lambda db, items: {description: "Groceries" for description, _ in items})
    with (
        patch("ingestion_worker.clients.drive_client.list_folder_pdf_files", return_value=files),
        patch("ingestion_worker.clients.drive_client.download_file", side_effect=fake_download),
        patch("ingestion_worker.extraction.service._pdf_to_page_images", return_value=[b"page"]),
        patch("ingestion_worker.extraction.service.extract_statement_raw", side_effect=responses),
        patch("ingestion_worker.orchestrator.pipeline.classify_batch", side_effect=classify),
    ):
        pipeline.process_run(db_session, run)
    db_session.refresh(run)
    return run


class TestAccountSectionsInThePipeline:
    """Epic 13 (WR-49..WR-51): every statement resolves its account sections, records one
    StatementAccount per section, and links each transaction to its section."""

    def test_a_single_account_statement_creates_an_account_a_section_and_linked_transactions(self, db_session):
        _seed_whitelist(db_session)
        response = json.dumps(
            {
                "bank_name": "OCBC Bank", "currency": "SGD", "confidence": "high", "statement_date": "2026-01-31",
                "sections": [
                    {
                        "account_identifier": "501-123-456", "account_type": "deposit", "closing_balance": 1234.56,
                        "closing_balance_date": "2026-01-31",
                        "transactions": [_txn_json("NTUC"), _txn_json("COLD STORAGE", "2026-01-16")],
                    }
                ],
            }
        )

        run = _ingest(db_session, [DriveFileRef(id="d1", name="jan.pdf")], [response])

        assert run.status == IngestionRunStatus.COMPLETED
        account = db_session.query(Account).one()
        assert (account.account_type, account.currency, account.name) == (AccountType.DEPOSIT, "SGD", "OCBC Bank 3456")
        section = db_session.query(StatementAccount).one()
        assert section.account_id == account.id
        assert str(section.closing_balance) == "1234.56" and str(section.closing_balance_date) == "2026-01-31"
        transactions = db_session.query(Transaction).all()
        assert len(transactions) == 2
        assert {t.statement_account_id for t in transactions} == {section.id}
        assert all(t.bank_statement_id == section.bank_statement_id for t in transactions)
        assert db_session.query(IngestionRunFile).one().transactions_extracted_count == 2

    def test_a_multi_account_statement_gets_one_section_per_account_with_the_right_transactions(self, db_session):
        _seed_whitelist(db_session)
        response = _sectioned_response(
            {"account_identifier": "111", "account_type": "deposit", "transactions": [_txn_json("SALARY"), _txn_json("RENT", "2026-01-20")]},
            {"account_identifier": "4111-1111", "account_type": "credit_card", "transactions": [_txn_json("AMAZON", "2026-01-18")]},
        )

        run = _ingest(db_session, [DriveFileRef(id="d1", name="combined.pdf")], [response])

        assert run.status == IngestionRunStatus.COMPLETED
        accounts = {a.account_type: a for a in db_session.query(Account).all()}
        assert set(accounts) == {AccountType.DEPOSIT, AccountType.CREDIT_CARD}
        by_account = {}
        for txn in db_session.query(Transaction).all():
            section = db_session.get(StatementAccount, txn.statement_account_id)
            by_account.setdefault(section.account_id, set()).add(txn.description)
        assert by_account[accounts[AccountType.DEPOSIT].id] == {"SALARY", "RENT"}
        assert by_account[accounts[AccountType.CREDIT_CARD].id] == {"AMAZON"}
        assert db_session.query(StatementAccount).count() == 2

    def test_a_flat_reply_still_creates_one_account_and_links_its_transactions(self, db_session):
        _seed_whitelist(db_session)

        _ingest(db_session, [DriveFileRef(id="d1", name="old-shape.pdf")], [_VALID_EXTRACTION_RESPONSE])

        assert db_session.query(Account).count() == 1
        assert db_session.query(StatementAccount).count() == 1
        assert db_session.query(Transaction).one().statement_account_id is not None

    def test_the_same_account_in_two_statements_is_one_account_with_two_sections(self, db_session):
        _seed_whitelist(db_session)
        jan = _sectioned_response({"account_identifier": "501-123-456", "transactions": [_txn_json("A")]})
        feb = _sectioned_response({"account_identifier": "501 123 456", "transactions": [_txn_json("B", "2026-02-10")]}, bank="OCBC")

        _ingest(db_session, [DriveFileRef(id="d1", name="jan.pdf"), DriveFileRef(id="d2", name="feb.pdf")], [jan, feb])

        assert db_session.query(Account).count() == 1
        assert db_session.query(StatementAccount).count() == 2

    def test_each_section_is_converted_with_its_own_currency(self, db_session):
        _seed_whitelist(db_session)
        response = _sectioned_response(
            {"account_identifier": "111", "currency": "SGD", "transactions": [_txn_json("LOCAL", amount=10)]},
            {"account_identifier": "222", "currency": "USD", "transactions": [_txn_json("ABROAD", amount=10, printed_sgd=13.5)]},
        )

        _ingest(db_session, [DriveFileRef(id="d1", name="multi-ccy.pdf")], [response])

        local = db_session.query(Transaction).filter_by(description="LOCAL").one()
        abroad = db_session.query(Transaction).filter_by(description="ABROAD").one()
        assert (local.currency, str(local.converted_amount_sgd)) == ("SGD", "10.00")
        assert (abroad.currency, str(abroad.converted_amount_sgd)) == ("USD", "13.50")
        assert {a.currency for a in db_session.query(Account).all()} == {"SGD", "USD"}

    def test_a_failed_extraction_creates_no_account_and_no_section(self, db_session):
        _seed_whitelist(db_session)

        run = _ingest(db_session, [DriveFileRef(id="d1", name="bad.pdf")], ["not valid json"])

        assert run.status == IngestionRunStatus.COMPLETED_WITH_FAILURES
        assert db_session.query(Account).count() == 0
        assert db_session.query(StatementAccount).count() == 0

    def test_a_file_that_fails_midway_leaves_nothing_behind_but_earlier_files_stay(self, db_session):
        """The savepoint around each file: the statement, accounts and sections the failing file had
        already written are discarded, so it is not skipped as a 'duplicate' next time; the earlier
        file (committed at its own end) is untouched."""
        _seed_whitelist(db_session)
        good = _sectioned_response({"account_identifier": "111", "transactions": [_txn_json("GOOD")]})
        doomed = _sectioned_response({"account_identifier": "999", "transactions": [_txn_json("DOOMED")]})
        calls = {"n": 0}

        def classify(db, items):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("simulated crash after the account, statement and section were written")
            return {description: "Groceries" for description, _ in items}

        run = _ingest(
            db_session,
            [DriveFileRef(id="d1", name="good.pdf"), DriveFileRef(id="d2", name="doomed.pdf")],
            [good, doomed],
            classify=classify,
        )

        assert run.status == IngestionRunStatus.FAILED
        assert [a.name for a in db_session.query(Account).all()] == ["OCBC Bank 111"]  # no account for 999
        assert db_session.query(StatementAccount).count() == 1
        assert [t.description for t in db_session.query(Transaction).all()] == ["GOOD"]
        assert db_session.query(BankStatement).count() == 1  # the doomed file's statement row is gone too


# --------------------------------------------------------------------------------------------
# Epic 14 (Probable Duplicate Statement Detection): the two checks in the per-file flow
# --------------------------------------------------------------------------------------------

import hashlib  # noqa: E402
import logging  # noqa: E402
from datetime import date  # noqa: E402

import pytest  # noqa: E402
from duplicates_helpers import extracted as _extracted_statement  # noqa: E402
from duplicates_helpers import june as _june  # noqa: E402
from duplicates_helpers import make_statement as _make_held  # noqa: E402
from transactagent_db.models import (  # noqa: E402
    DuplicateComparison,
    KnownFile,
    KnownFileState,
)

from ingestion_worker import config as _worker_config  # noqa: E402
from ingestion_worker.duplicates import service as _duplicates_service  # noqa: E402

_HELD = "1" * 64


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _run_files(db, files, *, backfill_mode=False):
    """Run the pipeline over `files`: a list of (file name, pdf bytes, ExtractedStatement). Returns
    (run, extract_mock) so a test can assert extraction was or was not called."""
    refs = [DriveFileRef(id=f"id-{name}", name=name) for name, _b, _e in files]
    contents = {f"id-{name}": pdf for name, pdf, _e in files}
    results = {pdf: statement for _n, pdf, statement in files}
    run = _make_run(db)
    with (
        patch("ingestion_worker.clients.drive_client.list_folder_pdf_files", return_value=refs),
        patch("ingestion_worker.clients.drive_client.download_file", side_effect=lambda _db, ref: contents[ref.id]),
        patch("ingestion_worker.orchestrator.pipeline.extract_statement", side_effect=lambda pdf: results[pdf]) as extract,
        patch("ingestion_worker.orchestrator.pipeline.classify_batch", return_value={}),
    ):
        pipeline.process_run(db, run, backfill_mode=backfill_mode)
    db.refresh(run)
    return run, extract


def _comparison(db):
    comparison = DuplicateComparison(
        earlier_content_hash=_HELD, earlier_period_start=date(2026, 6, 2), earlier_period_end=date(2026, 6, 30),
        earlier_transaction_count=5, later_content_hash="f" * 64, later_period_start=date(2026, 6, 2),
        later_period_end=date(2026, 6, 30), later_transaction_count=5, matched_count=5, match_ratio=1,
        reason="5 of 5 transactions match",
    )
    db.add(comparison)
    db.flush()
    return comparison


@pytest.fixture
def detection_on(monkeypatch):
    monkeypatch.setattr(_worker_config.settings, "duplicate_detection_enabled", True)
    monkeypatch.setattr(_worker_config.settings, "duplicate_match_ratio", 0.80)
    monkeypatch.setattr(_worker_config.settings, "duplicate_min_transactions", 3)


def _counts(db):
    return {
        "statements": db.query(BankStatement).count(),
        "transactions": db.query(Transaction).count(),
        "accounts": db.query(Account).count(),
        "sections": db.query(StatementAccount).count(),
    }


class TestRememberedFileCheck:
    """WR-61: check 1, before extraction, always on."""

    @pytest.mark.parametrize("state", [KnownFileState.PROBABLE_DUPLICATE, KnownFileState.CONFIRMED_DUPLICATE])
    def test_a_remembered_file_is_skipped_without_being_read(self, db_session, state):
        _seed_whitelist(db_session)
        pdf = b"remembered-bytes"
        comparison = _comparison(db_session)
        db_session.add(KnownFile(pdf_content_hash=_sha(pdf), state=state, matched_statement_hash=_HELD, comparison_id=comparison.id))
        db_session.flush()

        run, extract = _run_files(db_session, [("later.pdf", pdf, _extracted_statement(_june(5)))])

        extract.assert_not_called()  # no Gemini call (NFR-PD-2)
        row = db_session.query(IngestionRunFile).one()
        assert row.outcome == IngestionRunFileOutcome.SKIPPED_PROBABLE_DUPLICATE
        assert row.duplicate_comparison_id == comparison.id and row.bank_statement_id is None
        assert run.files_skipped_count == 1 and run.files_failed_count == 0
        assert run.status == IngestionRunStatus.COMPLETED  # a skip is never a failure (BR-52)

    def test_it_applies_even_when_detection_is_switched_off(self, db_session, monkeypatch):
        monkeypatch.setattr(_worker_config.settings, "duplicate_detection_enabled", False)
        _seed_whitelist(db_session)
        pdf = b"remembered-bytes"
        comparison = _comparison(db_session)
        db_session.add(KnownFile(pdf_content_hash=_sha(pdf), state=KnownFileState.CONFIRMED_DUPLICATE, matched_statement_hash=_HELD, comparison_id=comparison.id))
        db_session.flush()

        _run, extract = _run_files(db_session, [("later.pdf", pdf, _extracted_statement(_june(5)))])

        extract.assert_not_called()

    def test_an_overridden_file_is_ingested_and_exempt_from_the_similarity_check(self, db_session, detection_on):
        _seed_whitelist(db_session)
        _make_held(db_session, h=_HELD, rows=_june(5))
        pdf = b"overridden-bytes"
        comparison = _comparison(db_session)
        db_session.add(KnownFile(pdf_content_hash=_sha(pdf), state=KnownFileState.OVERRIDDEN, matched_statement_hash=_HELD, comparison_id=comparison.id))
        db_session.flush()

        run, extract = _run_files(db_session, [("later.pdf", pdf, _extracted_statement(_june(5)))])

        extract.assert_called_once()
        assert db_session.query(BankStatement).count() == 2  # ingested, though it duplicates the held one
        row = db_session.query(IngestionRunFile).one()
        assert row.outcome == IngestionRunFileOutcome.PROCESSED
        assert run.files_processed_count == 1

    def test_an_exact_duplicate_still_wins_and_is_unchanged(self, db_session, detection_on):
        """NFR-PD-6: the exact-bytes check runs first."""
        _seed_whitelist(db_session)
        pdf = b"same-bytes"
        _make_held(db_session, h=_sha(pdf), rows=_june(5))

        _run, extract = _run_files(db_session, [("again.pdf", pdf, _extracted_statement(_june(5)))])

        extract.assert_not_called()
        assert db_session.query(IngestionRunFile).one().outcome == IngestionRunFileOutcome.SKIPPED_DUPLICATE


class TestProbableDuplicateCheck:
    """WR-62: check 2, after extraction and before anything is created."""

    def test_a_probable_duplicate_is_skipped_and_creates_nothing(self, db_session, detection_on):
        _seed_whitelist(db_session)
        _make_held(db_session, h=_HELD, rows=_june(5), file_name="JUN 2026_1.pdf")
        before = _counts(db_session)

        run, extract = _run_files(db_session, [("JUN 2026_2.pdf", b"second-copy", _extracted_statement(_june(5)))])

        extract.assert_called_once()  # it had to be read once to be judged
        assert _counts(db_session) == before  # no statement, transaction, account or section
        row = db_session.query(IngestionRunFile).filter_by(drive_file_name="JUN 2026_2.pdf").one()
        assert row.outcome == IngestionRunFileOutcome.SKIPPED_PROBABLE_DUPLICATE
        assert row.bank_statement_id is None and row.transactions_extracted_count == 5
        comparison = db_session.get(DuplicateComparison, row.duplicate_comparison_id)
        assert comparison.earlier_file_name == "JUN 2026_1.pdf" and comparison.later_file_name == "JUN 2026_2.pdf"
        known = db_session.query(KnownFile).one()
        assert known.pdf_content_hash == _sha(b"second-copy") and known.state == KnownFileState.PROBABLE_DUPLICATE
        assert known.matched_statement_hash == _HELD
        assert run.files_skipped_count == 1 and run.status == IngestionRunStatus.COMPLETED

    def test_the_skip_is_remembered_so_the_next_run_does_not_read_the_file_again(self, db_session, detection_on):
        _seed_whitelist(db_session)
        _make_held(db_session, h=_HELD, rows=_june(5))
        files = [("copy.pdf", b"second-copy", _extracted_statement(_june(5)))]
        _run_files(db_session, files)

        _run, extract = _run_files(db_session, files)

        extract.assert_not_called()
        outcomes = [r.outcome for r in db_session.query(IngestionRunFile).order_by(IngestionRunFile.processed_at, IngestionRunFile.id)]
        assert outcomes == [IngestionRunFileOutcome.SKIPPED_PROBABLE_DUPLICATE] * 2

    def test_two_new_files_that_duplicate_each_other_in_one_run(self, db_session, detection_on):
        """A-PD-7: the first is persisted, the second is flagged against it."""
        _seed_whitelist(db_session)

        run, _extract = _run_files(
            db_session,
            [("a.pdf", b"copy-a", _extracted_statement(_june(5))), ("b.pdf", b"copy-b", _extracted_statement(_june(5)))],
        )

        outcomes = {r.drive_file_name: r.outcome for r in db_session.query(IngestionRunFile)}
        assert outcomes == {"a.pdf": IngestionRunFileOutcome.PROCESSED, "b.pdf": IngestionRunFileOutcome.SKIPPED_PROBABLE_DUPLICATE}
        assert db_session.query(BankStatement).count() == 1
        assert run.files_processed_count == 1 and run.files_skipped_count == 1

    def test_a_statement_that_is_not_a_duplicate_ingests_normally(self, db_session, detection_on):
        _seed_whitelist(db_session)
        _make_held(db_session, h=_HELD, rows=_june(5, month=5))

        run, _ = _run_files(db_session, [("jun.pdf", b"june", _extracted_statement(_june(5, month=6)))])

        assert db_session.query(BankStatement).count() == 2 and run.files_processed_count == 1
        assert db_session.query(KnownFile).count() == 0

    def test_detection_off_skips_this_check(self, db_session, monkeypatch):
        monkeypatch.setattr(_worker_config.settings, "duplicate_detection_enabled", False)
        _seed_whitelist(db_session)
        _make_held(db_session, h=_HELD, rows=_june(5))

        _run_files(db_session, [("copy.pdf", b"second-copy", _extracted_statement(_june(5)))])

        assert db_session.query(BankStatement).count() == 2  # ingested: nothing judged it

    def test_a_raising_detector_fails_open_and_the_file_ingests(self, db_session, detection_on, caplog):
        _seed_whitelist(db_session)
        _make_held(db_session, h=_HELD, rows=_june(5))

        with (
            patch.object(_duplicates_service, "find_probable_duplicate_of", side_effect=RuntimeError("detector bug")),
            caplog.at_level(logging.WARNING),
        ):
            run, _ = _run_files(db_session, [("copy.pdf", b"second-copy", _extracted_statement(_june(5)))])

        assert db_session.query(BankStatement).count() == 2 and run.files_processed_count == 1
        assert run.files_failed_count == 0
        assert "the duplicate check failed" in caplog.text

    def test_a_database_error_while_judging_does_not_poison_the_files_transaction(self, db_session, detection_on):
        """The check runs in a savepoint, so even a failing SQL statement leaves the session usable."""
        _seed_whitelist(db_session)
        _make_held(db_session, h=_HELD, rows=_june(5))

        def broken(db, *_a, **_k):
            db.execute(__import__("sqlalchemy").text("SELECT * FROM table_that_does_not_exist"))

        with patch.object(_duplicates_service, "find_probable_duplicate_of", side_effect=broken):
            run, _ = _run_files(db_session, [("copy.pdf", b"second-copy", _extracted_statement(_june(5)))])

        assert run.files_processed_count == 1 and run.files_failed_count == 0

    def test_a_failure_after_recording_the_skip_leaves_no_remembered_file_behind(self, db_session, detection_on):
        """The whole file is one savepoint: if recording the run file fails, the remembered file and
        comparison written a moment earlier are discarded with it."""
        _seed_whitelist(db_session)
        _make_held(db_session, h=_HELD, rows=_june(5))
        real = pipeline.orchestrator_repository.record_run_file

        def explode_on_skip(db, run, **kwargs):
            if kwargs.get("outcome") == IngestionRunFileOutcome.SKIPPED_PROBABLE_DUPLICATE:
                raise RuntimeError("cannot record")
            return real(db, run, **kwargs)

        with patch.object(pipeline.orchestrator_repository, "record_run_file", side_effect=explode_on_skip):
            run, _ = _run_files(db_session, [("copy.pdf", b"second-copy", _extracted_statement(_june(5)))])

        assert run.status == IngestionRunStatus.FAILED
        assert db_session.query(KnownFile).count() == 0 and db_session.query(DuplicateComparison).count() == 0


_LARGE_STATEMENT = [*_june(5), *((date(2026, 6, 20 + i), f"{500 + i}.00", f"EXTRA {i}") for i in range(10))]


class TestBackfillMode:
    """WR-62 / WR-69: the Backfill Tool's reingest."""

    def test_ordinary_ingestion_skips_a_larger_file_that_contains_a_held_one(self, db_session, detection_on):
        """Question 1 = C at ingestion: skipped, with the size difference stated prominently."""
        _seed_whitelist(db_session)
        _make_held(db_session, h=_HELD, rows=_june(5))

        _run_files(db_session, [("larger.pdf", b"larger", _extracted_statement(_LARGE_STATEMENT))])

        assert db_session.query(BankStatement).count() == 1
        reason = db_session.query(DuplicateComparison).one().reason
        assert "This file is the larger one: it has 15 transactions against 5" in reason

    def test_the_backfill_reingest_does_not_skip_a_different_size_match(self, db_session, detection_on):
        _seed_whitelist(db_session)
        _make_held(db_session, h=_HELD, rows=_june(5))

        _run_files(db_session, [("larger.pdf", b"larger", _extracted_statement(_LARGE_STATEMENT))], backfill_mode=True)

        assert db_session.query(BankStatement).count() == 2  # both kept; the scan will list the pair
        assert db_session.query(KnownFile).count() == 0

    def test_the_backfill_reingest_skips_a_same_size_match_even_when_the_switch_is_off(self, db_session, monkeypatch):
        monkeypatch.setattr(_worker_config.settings, "duplicate_detection_enabled", False)
        _seed_whitelist(db_session)
        _make_held(db_session, h=_HELD, rows=_june(5))

        run, _ = _run_files(db_session, [("copy.pdf", b"second-copy", _extracted_statement(_june(5)))], backfill_mode=True)

        assert db_session.query(BankStatement).count() == 1 and run.files_skipped_count == 1
