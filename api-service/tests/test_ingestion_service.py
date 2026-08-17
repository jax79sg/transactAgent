import uuid

import pytest
from transactagent_db.models import IngestionRun, IngestionRunStatus, User

from api_service.errors import (
    IngestionRunAlreadyActiveError,
    NotFoundError,
    RunNotCancellableError,
)
from api_service.ingestion import service


def _make_user(db):
    user = User(username=f"user-{uuid.uuid4()}", password_hash="hashed")
    db.add(user)
    db.flush()
    return user


class TestStartRun:
    def test_start_run_when_none_active_succeeds(self, db_session):
        user = _make_user(db_session)
        run = service.start_run(db_session, user.id)
        assert run.status == IngestionRunStatus.QUEUED

    def test_start_run_when_one_already_active_is_rejected(self, db_session):
        user = _make_user(db_session)
        first_run = service.start_run(db_session, user.id)
        with pytest.raises(IngestionRunAlreadyActiveError) as exc_info:
            service.start_run(db_session, user.id)
        assert exc_info.value.details["existingRunId"] == str(first_run.id)


class TestGetRunStatus:
    def test_unknown_run_id_raises_not_found(self, db_session):
        with pytest.raises(NotFoundError):
            service.get_run_status(db_session, uuid.uuid4())


class TestCancelRun:
    """cancel_run only ever sets cancel_requested_at (never `status` -- that's the
    worker's sole responsibility, checked between files; see aidlc-docs/audit.md
    2026-08-05) so the API and worker processes never race on the same column."""

    def test_unknown_run_id_raises_not_found(self, db_session):
        with pytest.raises(NotFoundError):
            service.cancel_run(db_session, uuid.uuid4())

    def test_cancelling_a_running_run_sets_requested_at_not_status(self, db_session):
        user = _make_user(db_session)
        run = IngestionRun(triggered_by_user_id=user.id, status=IngestionRunStatus.RUNNING)
        db_session.add(run)
        db_session.flush()

        result = service.cancel_run(db_session, run.id)

        assert result.cancel_requested_at is not None
        assert result.status == IngestionRunStatus.RUNNING  # unchanged -- only the worker sets this

    def test_cancelling_a_queued_run_is_allowed(self, db_session):
        user = _make_user(db_session)
        run = service.start_run(db_session, user.id)

        result = service.cancel_run(db_session, run.id)

        assert result.cancel_requested_at is not None
        assert result.status == IngestionRunStatus.QUEUED

    @pytest.mark.parametrize(
        "terminal_status",
        [
            IngestionRunStatus.COMPLETED,
            IngestionRunStatus.COMPLETED_WITH_FAILURES,
            IngestionRunStatus.FAILED,
            IngestionRunStatus.CANCELLED,
        ],
    )
    def test_cancelling_an_already_terminal_run_is_rejected(self, db_session, terminal_status):
        user = _make_user(db_session)
        run = IngestionRun(triggered_by_user_id=user.id, status=terminal_status)
        db_session.add(run)
        db_session.flush()

        with pytest.raises(RunNotCancellableError) as exc_info:
            service.cancel_run(db_session, run.id)
        assert exc_info.value.details["status"] == terminal_status.value

    def test_cancelling_twice_is_idempotent(self, db_session):
        user = _make_user(db_session)
        run = IngestionRun(triggered_by_user_id=user.id, status=IngestionRunStatus.RUNNING)
        db_session.add(run)
        db_session.flush()

        first = service.cancel_run(db_session, run.id)
        first_requested_at = first.cancel_requested_at
        second = service.cancel_run(db_session, run.id)

        assert second.cancel_requested_at == first_requested_at  # not bumped on a second call
