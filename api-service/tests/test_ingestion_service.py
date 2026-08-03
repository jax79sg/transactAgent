import uuid

import pytest

from api_service.errors import IngestionRunAlreadyActiveError, NotFoundError
from api_service.ingestion import service
from transactagent_db.models import IngestionRunStatus, User


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
