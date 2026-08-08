from datetime import date, datetime, timezone

from transactagent_db.models import BackupRun, BackupRunFailureCategory, BackupRunOutcome


def _make_backup_run(db, **overrides):
    defaults = dict(
        backup_date=date(2026, 8, 8),
        started_at=datetime(2026, 8, 8, 2, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 8, 8, 2, 0, 5, tzinfo=timezone.utc),
        outcome=BackupRunOutcome.SUCCESS,
        transaction_count=2174,
        backup_filename="transactions-backup-20260808T020000Z.csv",
    )
    defaults.update(overrides)
    run = BackupRun(**defaults)
    db.add(run)
    db.flush()
    return run


class TestBackupStatusApi:
    def test_requires_auth(self, client):
        response = client.get("/backups/status")
        assert response.status_code == 401

    def test_no_prior_backup_returns_null_outcome(self, client, auth_headers):
        response = client.get("/backups/status", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["outcome"] is None
        assert body["lastRunAt"] is None

    def test_reflects_successful_backup(self, client, auth_headers, db_session):
        _make_backup_run(db_session)

        response = client.get("/backups/status", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["outcome"] == "success"
        assert body["transactionCount"] == 2174
        assert body["backupFilename"] == "transactions-backup-20260808T020000Z.csv"

    def test_reflects_failed_backup_with_drive_connectivity_category(self, client, auth_headers, db_session):
        _make_backup_run(
            db_session,
            outcome=BackupRunOutcome.FAILED,
            failure_category=BackupRunFailureCategory.DRIVE_CONNECTIVITY,
            transaction_count=None,
            backup_filename=None,
        )

        response = client.get("/backups/status", headers=auth_headers)

        body = response.json()
        assert body["outcome"] == "failed"
        assert body["failureCategory"] == "drive_connectivity"
