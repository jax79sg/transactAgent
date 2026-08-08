"""Tests for backup/service.py (Epic 7, Nightly Transaction Backup).

Drive I/O (drive_client) and the repository layer are mocked -- this file covers
the Backup Manager's own decision logic (WR-11..15), not Drive API behavior
(that's test_drive_client.py) or schema constraints (that's the database unit's
test_models.py).
"""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError

from ingestion_worker.backup import service as backup_service
from ingestion_worker.clients.drive_client import DriveFileRef, DriveNotConnectedError
from ingestion_worker.clients.retry import TransientError
from transactagent_db.models import BackupRunFailureCategory, BackupRunOutcome


class TestIsBackupDueNow:
    """WR-11: due iff the schedule time has passed AND no attempt exists yet today."""

    def test_before_schedule_hour_is_not_due(self):
        fake_db = MagicMock()
        fake_now = datetime(2026, 8, 8, 1, 30)  # before the default 02:00 schedule hour
        with patch("ingestion_worker.backup.service.datetime") as mock_datetime:
            mock_datetime.now.return_value = fake_now
            result = backup_service.is_backup_due_now(fake_db)

        assert result is False

    def test_after_schedule_hour_with_no_prior_attempt_is_due(self):
        fake_db = MagicMock()
        fake_now = datetime(2026, 8, 8, 9, 0)  # well after 02:00 -- e.g. a catch-up scenario
        with (
            patch("ingestion_worker.backup.service.datetime") as mock_datetime,
            patch(
                "ingestion_worker.backup.service.backup_repository.find_backup_run_for_date", return_value=None
            ) as mock_find,
        ):
            mock_datetime.now.return_value = fake_now
            result = backup_service.is_backup_due_now(fake_db)

        assert result is True
        mock_find.assert_called_once_with(fake_db, date(2026, 8, 8))

    def test_after_schedule_hour_with_prior_attempt_today_is_not_due(self):
        """Covers both a prior success (no duplicate, US-7.1) and a prior failure
        (no same-night retry, FR-9) -- find_backup_run_for_date returning any row
        at all is sufficient, regardless of its outcome."""
        fake_db = MagicMock()
        fake_now = datetime(2026, 8, 8, 23, 0)
        with (
            patch("ingestion_worker.backup.service.datetime") as mock_datetime,
            patch(
                "ingestion_worker.backup.service.backup_repository.find_backup_run_for_date",
                return_value=MagicMock(),
            ),
        ):
            mock_datetime.now.return_value = fake_now
            result = backup_service.is_backup_due_now(fake_db)

        assert result is False


class TestRunBackup:
    """WR-12: exactly one BackupRun row written per attempt, no exception ever escapes."""

    def _fake_transaction(self, **overrides):
        txn = MagicMock()
        defaults = {
            "id": "txn-id",
            "bank_statement_id": "stmt-id",
            "transaction_date": date(2026, 8, 7),
            "description": "AMAZON SG",
            "out_flow": None,
            "in_flow": None,
            "currency": "SGD",
            "bank_name": "DBS",
            "category_id": "cat-id",
            "category_source": MagicMock(value="manual"),
            "converted_amount_sgd": None,
            "conversion_is_approximate": False,
            "conversion_unavailable": False,
            "fx_rate_used_id": None,
            "created_at": datetime(2026, 8, 7, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 8, 7, tzinfo=timezone.utc),
        }
        defaults.update(overrides)
        for key, value in defaults.items():
            setattr(txn, key, value)
        return txn

    def test_success_path_uploads_and_records_success(self):
        fake_db = MagicMock()
        fake_db.scalars.return_value = [self._fake_transaction()]

        with (
            patch("ingestion_worker.backup.service.drive_client.ensure_backup_folder_exists", return_value="folder-id"),
            patch("ingestion_worker.backup.service.drive_client.upload_file") as mock_upload,
            patch("ingestion_worker.backup.service.drive_client.list_backup_folder_files", return_value=[]),
            patch("ingestion_worker.backup.service.backup_repository.record_backup_run") as mock_record,
        ):
            backup_service.run_backup(fake_db)

        mock_upload.assert_called_once()
        upload_kwargs = mock_upload.call_args
        assert upload_kwargs.args[1] == "folder-id"
        record_kwargs = mock_record.call_args.kwargs
        assert record_kwargs["outcome"] == BackupRunOutcome.SUCCESS
        assert record_kwargs["transaction_count"] == 1
        assert record_kwargs.get("failure_category") is None
        assert record_kwargs["backup_filename"].startswith("transactions-backup-")

    def test_drive_not_connected_records_drive_connectivity_failure(self):
        fake_db = MagicMock()
        fake_db.scalars.return_value = []

        with (
            patch(
                "ingestion_worker.backup.service.drive_client.ensure_backup_folder_exists",
                side_effect=DriveNotConnectedError("not connected"),
            ),
            patch("ingestion_worker.backup.service.backup_repository.record_backup_run") as mock_record,
        ):
            backup_service.run_backup(fake_db)  # must not raise

        record_kwargs = mock_record.call_args.kwargs
        assert record_kwargs["outcome"] == BackupRunOutcome.FAILED
        assert record_kwargs["failure_category"] == BackupRunFailureCategory.DRIVE_CONNECTIVITY

    def test_transient_drive_error_records_drive_connectivity_failure(self):
        fake_db = MagicMock()
        fake_db.scalars.return_value = []

        with (
            patch(
                "ingestion_worker.backup.service.drive_client.ensure_backup_folder_exists",
                side_effect=TransientError("Drive rate limited"),
            ),
            patch("ingestion_worker.backup.service.backup_repository.record_backup_run") as mock_record,
        ):
            backup_service.run_backup(fake_db)  # must not raise

        record_kwargs = mock_record.call_args.kwargs
        assert record_kwargs["failure_category"] == BackupRunFailureCategory.DRIVE_CONNECTIVITY

    def test_http_error_records_drive_connectivity_failure(self):
        fake_db = MagicMock()
        fake_db.scalars.return_value = []
        fake_resp = MagicMock(status=403)
        http_error = HttpError(resp=fake_resp, content=b"forbidden")

        with (
            patch(
                "ingestion_worker.backup.service.drive_client.ensure_backup_folder_exists", side_effect=http_error
            ),
            patch("ingestion_worker.backup.service.backup_repository.record_backup_run") as mock_record,
        ):
            backup_service.run_backup(fake_db)  # must not raise

        record_kwargs = mock_record.call_args.kwargs
        assert record_kwargs["failure_category"] == BackupRunFailureCategory.DRIVE_CONNECTIVITY

    def test_unexpected_error_records_other_failure_and_never_raises(self):
        """WR-12's core guarantee: even a totally unexpected error (e.g. a DB
        error while querying transactions) must not escape run_backup()."""
        fake_db = MagicMock()
        fake_db.scalars.side_effect = RuntimeError("db connection lost")

        with patch("ingestion_worker.backup.service.backup_repository.record_backup_run") as mock_record:
            backup_service.run_backup(fake_db)  # must not raise

        record_kwargs = mock_record.call_args.kwargs
        assert record_kwargs["outcome"] == BackupRunOutcome.FAILED
        assert record_kwargs["failure_category"] == BackupRunFailureCategory.OTHER

    def test_exactly_one_backup_run_recorded_per_attempt(self):
        fake_db = MagicMock()
        fake_db.scalars.return_value = [self._fake_transaction()]

        with (
            patch("ingestion_worker.backup.service.drive_client.ensure_backup_folder_exists", return_value="folder-id"),
            patch("ingestion_worker.backup.service.drive_client.upload_file"),
            patch("ingestion_worker.backup.service.drive_client.list_backup_folder_files", return_value=[]),
            patch("ingestion_worker.backup.service.backup_repository.record_backup_run") as mock_record,
        ):
            backup_service.run_backup(fake_db)

        mock_record.assert_called_once()


class TestEnforceRetention:
    """WR-14/US-7.2: keeps the configured most-recent count, ignores non-matching
    filenames, only deletes true excess."""

    def _file(self, name, created_time):
        return DriveFileRef(id=name, name=name, created_time=created_time)

    def test_keeps_exactly_the_configured_most_recent_count(self):
        files = [
            self._file(f"transactions-backup-{i}.csv", f"2026-08-{i:02d}T02:00:00Z") for i in range(1, 10)
        ]  # 9 files, default retention count is 7
        with (
            patch("ingestion_worker.backup.service.drive_client.list_backup_folder_files", return_value=files),
            patch("ingestion_worker.backup.service.drive_client.delete_file") as mock_delete,
        ):
            backup_service._enforce_retention(db=MagicMock(), folder_id="folder-id")

        assert mock_delete.call_count == 2  # 9 - 7 = 2 oldest deleted
        deleted_ids = {call.args[1].id for call in mock_delete.call_args_list}
        assert deleted_ids == {"transactions-backup-1.csv", "transactions-backup-2.csv"}

    def test_no_deletion_when_at_or_under_the_limit(self):
        files = [self._file(f"transactions-backup-{i}.csv", f"2026-08-{i:02d}T02:00:00Z") for i in range(1, 6)]
        with (
            patch("ingestion_worker.backup.service.drive_client.list_backup_folder_files", return_value=files),
            patch("ingestion_worker.backup.service.drive_client.delete_file") as mock_delete,
        ):
            backup_service._enforce_retention(db=MagicMock(), folder_id="folder-id")

        mock_delete.assert_not_called()

    def test_ignores_files_not_matching_the_naming_convention(self):
        """NFR-4: a file that doesn't match this feature's naming convention is
        never a deletion candidate, even if there are more than 7 files total and
        it's the oldest."""
        files = [
            self._file("some-other-file.txt", "2026-08-01T00:00:00Z"),  # oldest, but not ours
        ] + [self._file(f"transactions-backup-{i}.csv", f"2026-08-{i:02d}T02:00:00Z") for i in range(1, 9)]
        with (
            patch("ingestion_worker.backup.service.drive_client.list_backup_folder_files", return_value=files),
            patch("ingestion_worker.backup.service.drive_client.delete_file") as mock_delete,
        ):
            backup_service._enforce_retention(db=MagicMock(), folder_id="folder-id")

        deleted_names = {call.args[1].name for call in mock_delete.call_args_list}
        assert "some-other-file.txt" not in deleted_names
        assert len(deleted_names) == 1  # 8 matching files - 7 kept = 1 deleted
