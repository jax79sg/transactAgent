import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from transactagent_db.models import (
    BankStatement,
    Category,
    CategorySource,
    IngestionRun,
    IngestionRunStatus,
    RecategorizationJob,
    RecategorizationJobStatus,
    Transaction,
)

from api_service.background_activity import repository


def _make_ingestion_run(db, user_id, **overrides):
    defaults = {"status": IngestionRunStatus.QUEUED, "triggered_by_user_id": user_id}
    defaults.update(overrides)
    run = IngestionRun(**defaults)
    db.add(run)
    db.flush()
    return run


def _make_transaction(db):
    statement = BankStatement(drive_file_id=uuid.uuid4().hex, pdf_content_hash=uuid.uuid4().hex + uuid.uuid4().hex[:32])
    category = Category(name=f"Test-{uuid.uuid4().hex[:8]}", active=True, is_reserved=False)
    db.add_all([statement, category])
    db.flush()
    txn = Transaction(
        bank_statement_id=statement.id,
        transaction_date=date(2026, 1, 1),
        description="Test transaction",
        out_flow=Decimal("10.00"),
        in_flow=None,
        currency="SGD",
        bank_name="DBS",
        category_id=category.id,
        category_source=CategorySource.MANUAL,
    )
    db.add(txn)
    db.flush()
    return txn


def _make_recategorization_job(db, source_transaction_id, **overrides):
    defaults = {"source_transaction_id": source_transaction_id, "status": RecategorizationJobStatus.QUEUED}
    defaults.update(overrides)
    job = RecategorizationJob(**defaults)
    db.add(job)
    db.flush()
    return job


class TestGetCurrentActivity:
    def test_idle_when_nothing_running(self, db_session):
        assert repository.get_current_activity(db_session) is None

    def test_reports_running_ingestion_run(self, db_session, test_user):
        _make_ingestion_run(db_session, test_user.id, status=IngestionRunStatus.RUNNING)

        result = repository.get_current_activity(db_session)

        assert result is not None
        assert result[0] == "ingestion_run"

    def test_reports_running_recategorization_job(self, db_session):
        txn = _make_transaction(db_session)
        _make_recategorization_job(db_session, txn.id, status=RecategorizationJobStatus.RUNNING)

        result = repository.get_current_activity(db_session)

        assert result is not None
        assert result[0] == "recategorization_job"

    def test_ignores_queued_and_completed(self, db_session, test_user):
        _make_ingestion_run(db_session, test_user.id, status=IngestionRunStatus.QUEUED)
        _make_ingestion_run(
            db_session,
            test_user.id,
            status=IngestionRunStatus.COMPLETED,
            completed_at=datetime(2026, 8, 18, 9, 0, tzinfo=UTC),
        )

        assert repository.get_current_activity(db_session) is None

    def test_prefers_more_recently_started_if_both_somehow_running(self, db_session, test_user):
        """AR-35 defensive tie-break: the single-active-job invariant lives in the
        worker's poll loop, not a cross-table DB constraint, so this shouldn't happen
        in practice -- but the query must still resolve deterministically if it does."""
        txn = _make_transaction(db_session)
        _make_ingestion_run(
            db_session,
            test_user.id,
            status=IngestionRunStatus.RUNNING,
            started_at=datetime(2026, 8, 18, 8, 0, tzinfo=UTC),
        )
        _make_recategorization_job(
            db_session,
            txn.id,
            status=RecategorizationJobStatus.RUNNING,
            created_at=datetime(2026, 8, 18, 9, 0, tzinfo=UTC),
        )

        result = repository.get_current_activity(db_session)

        assert result == ("recategorization_job", datetime(2026, 8, 18, 9, 0, tzinfo=UTC))


class TestGetRecentActivity:
    def test_empty_when_nothing_completed(self, db_session):
        assert repository.get_recent_activity(db_session) == []

    def test_returns_completed_ingestion_run(self, db_session, test_user):
        _make_ingestion_run(
            db_session,
            test_user.id,
            status=IngestionRunStatus.COMPLETED,
            completed_at=datetime(2026, 8, 18, 9, 0, tzinfo=UTC),
        )

        result = repository.get_recent_activity(db_session)

        assert len(result) == 1
        assert result[0][0] == "ingestion_run"

    def test_excludes_running_row_from_its_own_history(self, db_session, test_user):
        """AR-37: completed_at IS NOT NULL already excludes the running row."""
        _make_ingestion_run(db_session, test_user.id, status=IngestionRunStatus.RUNNING)

        assert repository.get_recent_activity(db_session) == []

    def test_combines_and_sorts_across_both_tables(self, db_session, test_user):
        txn = _make_transaction(db_session)
        _make_ingestion_run(
            db_session,
            test_user.id,
            status=IngestionRunStatus.COMPLETED,
            completed_at=datetime(2026, 8, 18, 8, 0, tzinfo=UTC),
        )
        _make_recategorization_job(
            db_session,
            txn.id,
            status=RecategorizationJobStatus.COMPLETED,
            completed_at=datetime(2026, 8, 18, 9, 0, tzinfo=UTC),
        )

        result = repository.get_recent_activity(db_session)

        assert [job_type for job_type, _ in result] == ["recategorization_job", "ingestion_run"]

    def test_respects_limit(self, db_session, test_user):
        for i in range(3):
            _make_ingestion_run(
                db_session,
                test_user.id,
                status=IngestionRunStatus.COMPLETED,
                completed_at=datetime(2026, 8, 18, 8, i, tzinfo=UTC),
            )

        result = repository.get_recent_activity(db_session, limit=2)

        assert len(result) == 2
