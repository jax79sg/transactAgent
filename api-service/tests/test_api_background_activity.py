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


class TestBackgroundActivitySummaryApi:
    def test_requires_auth(self, client):
        response = client.get("/background-activity/summary")
        assert response.status_code == 401

    def test_idle_and_no_history_returns_empty_shape(self, client, auth_headers):
        response = client.get("/background-activity/summary", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["current"] is None
        assert body["recent"] == []

    def test_reflects_running_ingestion_run(self, client, auth_headers, db_session, test_user):
        _make_ingestion_run(db_session, test_user.id, status=IngestionRunStatus.RUNNING)

        response = client.get("/background-activity/summary", headers=auth_headers)

        body = response.json()
        assert body["current"]["jobType"] == "ingestion_run"

    def test_reflects_recent_completions(self, client, auth_headers, db_session, test_user):
        txn = _make_transaction(db_session)
        db_session.add(
            RecategorizationJob(
                source_transaction_id=txn.id,
                status=RecategorizationJobStatus.COMPLETED,
                completed_at=datetime(2026, 8, 18, 9, 0, tzinfo=UTC),
            )
        )
        db_session.flush()

        response = client.get("/background-activity/summary", headers=auth_headers)

        body = response.json()
        assert body["current"] is None
        assert len(body["recent"]) == 1
        assert body["recent"][0]["jobType"] == "recategorization_job"
