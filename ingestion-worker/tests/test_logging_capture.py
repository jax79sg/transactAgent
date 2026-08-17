"""DbLogHandler writes to its own short-lived session via ingestion_worker.db.SessionLocal
(patched here to the test engine), which is a genuinely separate connection from
whatever created the run. The db_session fixture used elsewhere in this suite
deliberately can't be used to set up data for these tests: it wraps each test in an
outer, never-committed transaction (SAVEPOINT-based) so tests roll back cleanly, which
means even a real commit() from inside that fixture never becomes visible to a truly
separate connection -- exactly what these tests need to exercise. So run setup here
uses a plain Session(engine) with a real commit instead.
"""

import logging
import uuid
from unittest.mock import patch

from sqlalchemy.orm import Session, sessionmaker
from transactagent_db.models import (
    IngestionRun,
    IngestionRunLog,
    IngestionRunStatus,
    User,
)

from ingestion_worker import logging_capture
from ingestion_worker.logging_capture import DbLogHandler, set_current_run


def _make_committed_run(engine):
    with Session(engine) as session:
        user = User(username=f"account_owner-loghandler-{uuid.uuid4()}", password_hash="hashed")
        session.add(user)
        session.flush()
        run = IngestionRun(triggered_by_user_id=user.id, status=IngestionRunStatus.RUNNING)
        session.add(run)
        session.commit()
        return run.id


def _make_record(logger_name="ingestion_worker.orchestrator.pipeline", level=logging.INFO, msg="hello", exc_info=None):
    return logging.LogRecord(
        name=logger_name, level=level, pathname=__file__, lineno=1, msg=msg, args=(), exc_info=exc_info,
    )


class TestDbLogHandler:
    def test_noop_when_no_run_is_active(self, engine):
        with patch.object(logging_capture, "SessionLocal", sessionmaker(bind=engine)):
            set_current_run(None)
            DbLogHandler().emit(_make_record())
        # nothing to assert on directly -- absence of an exception (and no row written,
        # implicitly, since no run id existed to attach one to) is the point

    def test_writes_a_row_for_the_current_run(self, engine):
        run_id = _make_committed_run(engine)
        try:
            with patch.object(logging_capture, "SessionLocal", sessionmaker(bind=engine)):
                set_current_run(run_id)
                DbLogHandler().emit(_make_record(msg="Processing file 1/3: statement.pdf"))

            with Session(engine) as session:
                rows = session.query(IngestionRunLog).filter_by(ingestion_run_id=run_id).all()
            assert len(rows) == 1
            assert rows[0].message == "Processing file 1/3: statement.pdf"
            assert rows[0].level == "INFO"
            assert rows[0].logger_name == "ingestion_worker.orchestrator.pipeline"
        finally:
            set_current_run(None)

    def test_includes_traceback_for_exception_records(self, engine):
        run_id = _make_committed_run(engine)
        try:
            with patch.object(logging_capture, "SessionLocal", sessionmaker(bind=engine)):
                set_current_run(run_id)
                try:
                    raise RuntimeError("boom")
                except RuntimeError:
                    import sys

                    record = _make_record(level=logging.ERROR, msg="it broke", exc_info=sys.exc_info())
                DbLogHandler().emit(record)

            with Session(engine) as session:
                row = session.query(IngestionRunLog).filter_by(ingestion_run_id=run_id).one()
            assert "it broke" in row.message
            assert "RuntimeError: boom" in row.message
        finally:
            set_current_run(None)

    def test_a_write_failure_does_not_raise(self, engine):
        """logging.Handler.emit() must never raise -- a broken log sink must never break
        the pipeline emitting the log."""
        with patch.object(logging_capture, "SessionLocal", side_effect=RuntimeError("DB unreachable")):
            set_current_run("11111111-1111-1111-1111-111111111111")
            try:
                DbLogHandler().emit(_make_record())  # should not raise
            finally:
                set_current_run(None)
