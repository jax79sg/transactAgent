from datetime import date, datetime, timezone

from api_service.backup import service
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


class TestGetLatestBackupStatus:
    def test_no_prior_backup_returns_all_null_fields(self, db_session):
        result = service.get_latest_backup_status(db_session)

        assert result.outcome is None
        assert result.last_run_at is None
        assert result.failure_category is None
        assert result.transaction_count is None
        assert result.backup_filename is None

    def test_successful_backup_is_reflected(self, db_session):
        _make_backup_run(db_session)

        result = service.get_latest_backup_status(db_session)

        assert result.outcome == "success"
        assert result.failure_category is None
        assert result.transaction_count == 2174
        assert result.backup_filename == "transactions-backup-20260808T020000Z.csv"

    def test_failed_backup_includes_failure_category(self, db_session):
        _make_backup_run(
            db_session,
            outcome=BackupRunOutcome.FAILED,
            failure_category=BackupRunFailureCategory.DRIVE_CONNECTIVITY,
            transaction_count=None,
            backup_filename=None,
        )

        result = service.get_latest_backup_status(db_session)

        assert result.outcome == "failed"
        assert result.failure_category == "drive_connectivity"

    def test_most_recent_backup_date_wins(self, db_session):
        _make_backup_run(db_session, backup_date=date(2026, 8, 6), backup_filename="old.csv")
        _make_backup_run(db_session, backup_date=date(2026, 8, 7), backup_filename="newer.csv")

        result = service.get_latest_backup_status(db_session)

        assert result.backup_filename == "newer.csv"
