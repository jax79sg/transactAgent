"""Integration-style tests for the orchestrator pipeline: real Postgres (testcontainers),
external clients (Drive, Gemini, OpenRouter, FX) mocked at their client-module boundary.
"""

import json
import uuid
from unittest.mock import patch

from ingestion_worker.clients.drive_client import DriveFileRef
from ingestion_worker.orchestrator import pipeline
from transactagent_db.models import (
    Category,
    IngestionRun,
    IngestionRunFile,
    IngestionRunFileOutcome,
    IngestionRunStatus,
    Transaction,
    User,
)

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
