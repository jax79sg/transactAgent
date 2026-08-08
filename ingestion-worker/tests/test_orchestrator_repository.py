"""Tests for orchestrator/repository.py's stale-state recovery (real Postgres via
testcontainers). Regression coverage for a real incident: a categorization call
hung indefinitely (2026-08-04, see aidlc-docs/audit.md), leaving an IngestionRun
stuck "running" forever with no live process ever going to finish it -- and because
ingestion_runs has a single-active-run DB constraint, that orphaned row blocked
every future run. fail_stale_runs/fail_stale_recategorize_jobs are called once at
worker startup so a plain restart self-heals instead of needing manual DB surgery.
"""

import uuid
from datetime import datetime, timezone

from ingestion_worker.orchestrator import repository
from transactagent_db.models import (
    IngestionRun,
    IngestionRunStatus,
    RecategorizationJob,
    RecategorizationJobStatus,
    Transaction,
    User,
)


def _make_user(db):
    user = User(username=f"account_owner-{uuid.uuid4()}", password_hash="hashed")
    db.add(user)
    db.flush()
    return user


def _clean_slate(db):
    # Several repository functions under test (and elsewhere, e.g. pipeline.py via
    # update_run_progress) call db.commit() by design -- for the API service's
    # separate connection to see live progress -- which breaks db_session's
    # rollback-based isolation between tests (once anything commits on this
    # connection, the fixture's outer transaction.rollback() at teardown is a
    # no-op). That leaks QUEUED/RUNNING rows across test files sharing the same
    # session-scoped testcontainers Postgres. Clearing first makes these tests
    # self-contained regardless of run order/other tests' leftovers.
    repository.fail_stale_runs(db)
    repository.fail_stale_recategorize_jobs(db)


class TestFailStaleRuns:
    def test_running_run_is_marked_failed(self, db_session):
        _clean_slate(db_session)
        user = _make_user(db_session)
        run = IngestionRun(triggered_by_user_id=user.id, status=IngestionRunStatus.RUNNING)
        db_session.add(run)
        db_session.flush()

        count = repository.fail_stale_runs(db_session)

        db_session.refresh(run)
        assert count == 1
        assert run.status == IngestionRunStatus.FAILED
        assert run.completed_at is not None

    def test_queued_run_is_marked_failed(self, db_session):
        _clean_slate(db_session)
        user = _make_user(db_session)
        run = IngestionRun(triggered_by_user_id=user.id, status=IngestionRunStatus.QUEUED)
        db_session.add(run)
        db_session.flush()

        count = repository.fail_stale_runs(db_session)

        db_session.refresh(run)
        assert count == 1
        assert run.status == IngestionRunStatus.FAILED

    def test_already_terminal_runs_are_left_untouched(self, db_session):
        _clean_slate(db_session)
        user = _make_user(db_session)
        completed = IngestionRun(triggered_by_user_id=user.id, status=IngestionRunStatus.COMPLETED)
        failed = IngestionRun(triggered_by_user_id=user.id, status=IngestionRunStatus.FAILED)
        db_session.add_all([completed, failed])
        db_session.flush()

        count = repository.fail_stale_runs(db_session)

        assert count == 0
        db_session.refresh(completed)
        db_session.refresh(failed)
        assert completed.status == IngestionRunStatus.COMPLETED
        assert failed.status == IngestionRunStatus.FAILED

    def test_recovering_a_stale_run_frees_the_single_active_run_slot(self, db_session):
        # The whole point: the unique constraint that normally rejects a second
        # queued/running row must accept a new one once the orphaned row is failed.
        _clean_slate(db_session)
        user = _make_user(db_session)
        stale = IngestionRun(triggered_by_user_id=user.id, status=IngestionRunStatus.RUNNING)
        db_session.add(stale)
        db_session.flush()

        repository.fail_stale_runs(db_session)

        fresh = IngestionRun(triggered_by_user_id=user.id, status=IngestionRunStatus.QUEUED)
        db_session.add(fresh)
        db_session.flush()  # would raise IntegrityError if the stale row still counted as active

        assert repository.find_queued_run(db_session).id == fresh.id


class TestCancellation:
    """User-initiated cancellation (2026-08-05): cancel_requested_at is written only
    by the API, status=CANCELLED only by the worker -- see aidlc-docs/audit.md."""

    def test_is_cancellation_requested_false_by_default(self, db_session):
        _clean_slate(db_session)
        user = _make_user(db_session)
        run = IngestionRun(triggered_by_user_id=user.id, status=IngestionRunStatus.RUNNING)
        db_session.add(run)
        db_session.flush()

        assert repository.is_cancellation_requested(db_session, run.id) is False

    def test_is_cancellation_requested_true_once_set(self, db_session):
        _clean_slate(db_session)
        user = _make_user(db_session)
        run = IngestionRun(
            triggered_by_user_id=user.id,
            status=IngestionRunStatus.RUNNING,
            cancel_requested_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        db_session.flush()

        assert repository.is_cancellation_requested(db_session, run.id) is True

    def test_cancel_run_sets_status_and_completed_at(self, db_session):
        _clean_slate(db_session)
        user = _make_user(db_session)
        run = IngestionRun(
            triggered_by_user_id=user.id,
            status=IngestionRunStatus.RUNNING,
            cancel_requested_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        db_session.flush()

        repository.cancel_run(db_session, run)

        db_session.refresh(run)
        assert run.status == IngestionRunStatus.CANCELLED
        assert run.completed_at is not None

    def test_cancelling_frees_the_single_active_run_slot(self, db_session):
        # Same guarantee as recovering a stale run: a cancelled run must reach a
        # real terminal status immediately so the next run isn't blocked.
        _clean_slate(db_session)
        user = _make_user(db_session)
        run = IngestionRun(
            triggered_by_user_id=user.id,
            status=IngestionRunStatus.RUNNING,
            cancel_requested_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        db_session.flush()

        repository.cancel_run(db_session, run)

        fresh = IngestionRun(triggered_by_user_id=user.id, status=IngestionRunStatus.QUEUED)
        db_session.add(fresh)
        db_session.flush()  # would raise IntegrityError if the cancelled row still counted as active


class TestFailStaleRecategorizeJobs:
    def _make_transaction_for_job(self, db):
        from transactagent_db.models import Category, IngestionRun

        user = _make_user(db)
        category = Category(name=f"Cat-{uuid.uuid4()}", active=True)
        run = IngestionRun(triggered_by_user_id=user.id, status=IngestionRunStatus.COMPLETED)
        db.add_all([category, run])
        db.flush()
        from transactagent_db.models import BankStatement, CategorySource

        statement = BankStatement(drive_file_id=str(uuid.uuid4()), pdf_content_hash=str(uuid.uuid4()), bank_name="DBS")
        db.add(statement)
        db.flush()
        txn = Transaction(
            bank_statement_id=statement.id,
            transaction_date="2026-01-15",
            description="NTUC FAIRPRICE",
            out_flow=25.50,
            currency="SGD",
            bank_name="DBS",
            category_id=category.id,
            category_source=CategorySource.LLM,
        )
        db.add(txn)
        db.flush()
        return txn

    def test_running_job_is_marked_failed(self, db_session):
        _clean_slate(db_session)
        txn = self._make_transaction_for_job(db_session)
        job = RecategorizationJob(source_transaction_id=txn.id, status=RecategorizationJobStatus.RUNNING)
        db_session.add(job)
        db_session.flush()

        count = repository.fail_stale_recategorize_jobs(db_session)

        db_session.refresh(job)
        assert count == 1
        assert job.status == RecategorizationJobStatus.FAILED

    def test_already_terminal_job_is_left_untouched(self, db_session):
        txn = self._make_transaction_for_job(db_session)
        job = RecategorizationJob(source_transaction_id=txn.id, status=RecategorizationJobStatus.COMPLETED)
        db_session.add(job)
        db_session.flush()

        count = repository.fail_stale_recategorize_jobs(db_session)

        assert count == 0
        db_session.refresh(job)
        assert job.status == RecategorizationJobStatus.COMPLETED
