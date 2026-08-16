"""Tests for main.py's poll_once() dispatch logic (WR-8: one run OR one job per
cycle, never both, never two of the same). session_scope and the repository/pipeline
calls are mocked -- the pipeline's own logic is already covered by
test_orchestrator_pipeline.py; this file only tests the dispatch wiring.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from ingestion_worker import main


@contextmanager
def _fake_session_scope(fake_db):
    yield fake_db


class TestPollOnce:
    def test_queued_run_is_claimed_and_processed(self):
        fake_db = MagicMock()
        fake_run = MagicMock()

        with (
            patch("ingestion_worker.main.session_scope", side_effect=lambda: _fake_session_scope(fake_db)),
            patch("ingestion_worker.main.repository.find_queued_run", return_value=fake_run) as mock_find_run,
            patch("ingestion_worker.main.repository.claim_run") as mock_claim_run,
            patch("ingestion_worker.main.pipeline.process_run") as mock_process_run,
            patch("ingestion_worker.main.repository.find_queued_recategorize_job") as mock_find_job,
            patch.object(fake_db, "merge", return_value=fake_run),
        ):
            main.poll_once()

        mock_find_run.assert_called_once()
        mock_claim_run.assert_called_once_with(fake_db, fake_run)
        mock_process_run.assert_called_once()
        mock_find_job.assert_not_called()  # a run was found -- never also checks for a job this cycle

    def test_no_queued_run_falls_through_to_recategorize_job(self):
        fake_db = MagicMock()
        fake_job = MagicMock()

        with (
            patch("ingestion_worker.main.session_scope", side_effect=lambda: _fake_session_scope(fake_db)),
            patch("ingestion_worker.main.repository.find_queued_run", return_value=None),
            patch(
                "ingestion_worker.main.repository.find_queued_recategorize_job", return_value=fake_job
            ) as mock_find_job,
            patch("ingestion_worker.main.repository.claim_recategorize_job") as mock_claim_job,
            patch("ingestion_worker.main.pipeline.process_recategorize_job") as mock_process_job,
            patch.object(fake_db, "merge", return_value=fake_job),
        ):
            main.poll_once()

        mock_find_job.assert_called_once()
        mock_claim_job.assert_called_once_with(fake_db, fake_job)
        mock_process_job.assert_called_once()

    def test_nothing_queued_is_a_no_op(self):
        fake_db = MagicMock()

        with (
            patch("ingestion_worker.main.session_scope", side_effect=lambda: _fake_session_scope(fake_db)),
            patch("ingestion_worker.main.repository.find_queued_run", return_value=None),
            patch("ingestion_worker.main.repository.find_queued_recategorize_job", return_value=None),
            patch("ingestion_worker.main.pipeline.process_run") as mock_process_run,
            patch("ingestion_worker.main.pipeline.process_recategorize_job") as mock_process_job,
            patch("ingestion_worker.main.backup_service.is_backup_due_now", return_value=False),
            patch("ingestion_worker.main.backup_service.run_backup") as mock_run_backup,
            patch("ingestion_worker.main.recurring_payments_service.is_detection_scan_due_now", return_value=False),
            patch("ingestion_worker.main.recurring_payments_service.run_detection_scan") as mock_run_scan,
        ):
            main.poll_once()

        mock_process_run.assert_not_called()
        mock_process_job.assert_not_called()
        mock_run_backup.assert_not_called()
        mock_run_scan.assert_not_called()

    def test_backup_runs_only_when_nothing_else_queued_and_due(self):
        """Epic 7: the third, lowest-priority branch -- checked only when no run
        or job was found this cycle."""
        fake_db = MagicMock()

        with (
            patch("ingestion_worker.main.session_scope", side_effect=lambda: _fake_session_scope(fake_db)),
            patch("ingestion_worker.main.repository.find_queued_run", return_value=None),
            patch("ingestion_worker.main.repository.find_queued_recategorize_job", return_value=None),
            patch("ingestion_worker.main.backup_service.is_backup_due_now", return_value=True) as mock_due,
            patch("ingestion_worker.main.backup_service.run_backup") as mock_run_backup,
            patch("ingestion_worker.main.recurring_payments_service.is_detection_scan_due_now") as mock_scan_due,
        ):
            main.poll_once()

        mock_due.assert_called_once_with(fake_db)
        mock_run_backup.assert_called_once_with(fake_db)
        mock_scan_due.assert_not_called()  # a backup ran this cycle -- detection scan isn't even checked

    def test_detection_scan_runs_only_when_nothing_else_queued_and_due(self):
        """Epic 8: the fourth, lowest-priority branch -- checked only when no run,
        job, or backup was found/due this cycle."""
        fake_db = MagicMock()

        with (
            patch("ingestion_worker.main.session_scope", side_effect=lambda: _fake_session_scope(fake_db)),
            patch("ingestion_worker.main.repository.find_queued_run", return_value=None),
            patch("ingestion_worker.main.repository.find_queued_recategorize_job", return_value=None),
            patch("ingestion_worker.main.backup_service.is_backup_due_now", return_value=False),
            patch("ingestion_worker.main.recurring_payments_service.is_detection_scan_due_now", return_value=True) as mock_due,
            patch("ingestion_worker.main.recurring_payments_service.run_detection_scan") as mock_run_scan,
        ):
            main.poll_once()

        mock_due.assert_called_once_with(fake_db)
        mock_run_scan.assert_called_once_with(fake_db)

    def test_backup_is_never_checked_when_a_run_was_found(self):
        fake_db = MagicMock()
        fake_run = MagicMock()

        with (
            patch("ingestion_worker.main.session_scope", side_effect=lambda: _fake_session_scope(fake_db)),
            patch("ingestion_worker.main.repository.find_queued_run", return_value=fake_run),
            patch("ingestion_worker.main.repository.claim_run"),
            patch("ingestion_worker.main.pipeline.process_run"),
            patch("ingestion_worker.main.backup_service.is_backup_due_now") as mock_due,
            patch("ingestion_worker.main.recurring_payments_service.is_detection_scan_due_now") as mock_scan_due,
            patch("ingestion_worker.main.embedding_service.process_next_embedding_batch") as mock_embed,
            patch.object(fake_db, "merge", return_value=fake_run),
        ):
            main.poll_once()

        mock_due.assert_not_called()
        mock_scan_due.assert_not_called()
        mock_embed.assert_not_called()

    def test_backup_is_never_checked_when_a_job_was_found(self):
        fake_db = MagicMock()
        fake_job = MagicMock()

        with (
            patch("ingestion_worker.main.session_scope", side_effect=lambda: _fake_session_scope(fake_db)),
            patch("ingestion_worker.main.repository.find_queued_run", return_value=None),
            patch("ingestion_worker.main.repository.find_queued_recategorize_job", return_value=fake_job),
            patch("ingestion_worker.main.repository.claim_recategorize_job"),
            patch("ingestion_worker.main.pipeline.process_recategorize_job"),
            patch("ingestion_worker.main.backup_service.is_backup_due_now") as mock_due,
            patch("ingestion_worker.main.recurring_payments_service.is_detection_scan_due_now") as mock_scan_due,
            patch("ingestion_worker.main.embedding_service.process_next_embedding_batch") as mock_embed,
            patch.object(fake_db, "merge", return_value=fake_job),
        ):
            main.poll_once()

        mock_due.assert_not_called()
        mock_scan_due.assert_not_called()
        mock_embed.assert_not_called()

    def test_embedding_batch_runs_only_when_nothing_else_queued_and_due(self):
        """Epic 9 (services.md correction): the fifth, lowest-priority branch --
        checked only when no run, job, backup, or detection scan was found/due this
        cycle. Backlog-triggered, not time-triggered -- no "is due" check to mock,
        the batch call itself is a no-op when nothing is pending."""
        fake_db = MagicMock()

        with (
            patch("ingestion_worker.main.session_scope", side_effect=lambda: _fake_session_scope(fake_db)),
            patch("ingestion_worker.main.repository.find_queued_run", return_value=None),
            patch("ingestion_worker.main.repository.find_queued_recategorize_job", return_value=None),
            patch("ingestion_worker.main.backup_service.is_backup_due_now", return_value=False),
            patch("ingestion_worker.main.recurring_payments_service.is_detection_scan_due_now", return_value=False),
            patch("ingestion_worker.main.embedding_service.process_next_embedding_batch") as mock_embed,
        ):
            main.poll_once()

        mock_embed.assert_called_once_with(fake_db)

    def test_embedding_batch_is_never_checked_when_a_backup_ran(self):
        fake_db = MagicMock()

        with (
            patch("ingestion_worker.main.session_scope", side_effect=lambda: _fake_session_scope(fake_db)),
            patch("ingestion_worker.main.repository.find_queued_run", return_value=None),
            patch("ingestion_worker.main.repository.find_queued_recategorize_job", return_value=None),
            patch("ingestion_worker.main.backup_service.is_backup_due_now", return_value=True),
            patch("ingestion_worker.main.backup_service.run_backup"),
            patch("ingestion_worker.main.recurring_payments_service.is_detection_scan_due_now") as mock_scan_due,
            patch("ingestion_worker.main.embedding_service.process_next_embedding_batch") as mock_embed,
        ):
            main.poll_once()

        mock_scan_due.assert_not_called()
        mock_embed.assert_not_called()

    def test_embedding_batch_is_never_checked_when_a_detection_scan_ran(self):
        fake_db = MagicMock()

        with (
            patch("ingestion_worker.main.session_scope", side_effect=lambda: _fake_session_scope(fake_db)),
            patch("ingestion_worker.main.repository.find_queued_run", return_value=None),
            patch("ingestion_worker.main.repository.find_queued_recategorize_job", return_value=None),
            patch("ingestion_worker.main.backup_service.is_backup_due_now", return_value=False),
            patch("ingestion_worker.main.recurring_payments_service.is_detection_scan_due_now", return_value=True),
            patch("ingestion_worker.main.recurring_payments_service.run_detection_scan"),
            patch("ingestion_worker.main.embedding_service.process_next_embedding_batch") as mock_embed,
        ):
            main.poll_once()

        mock_embed.assert_not_called()


class TestRecoverStaleState:
    """Regression coverage for a real incident: a categorization call hung
    indefinitely (2026-08-04), leaving an IngestionRun stuck "running" forever and
    blocking every future run via the single-active-run DB constraint. This is
    called once at startup so a plain restart self-heals instead of needing manual
    DB surgery."""

    def test_logs_a_warning_when_stale_state_is_found(self):
        fake_db = MagicMock()
        with (
            patch("ingestion_worker.main.session_scope", side_effect=lambda: _fake_session_scope(fake_db)),
            patch("ingestion_worker.main.repository.fail_stale_runs", return_value=1) as mock_fail_runs,
            patch("ingestion_worker.main.repository.fail_stale_recategorize_jobs", return_value=2) as mock_fail_jobs,
            patch("ingestion_worker.main.logger") as mock_logger,
        ):
            main.recover_stale_state()

        mock_fail_runs.assert_called_once_with(fake_db)
        mock_fail_jobs.assert_called_once_with(fake_db)
        mock_logger.warning.assert_called_once()

    def test_no_warning_when_nothing_is_stale(self):
        fake_db = MagicMock()
        with (
            patch("ingestion_worker.main.session_scope", side_effect=lambda: _fake_session_scope(fake_db)),
            patch("ingestion_worker.main.repository.fail_stale_runs", return_value=0),
            patch("ingestion_worker.main.repository.fail_stale_recategorize_jobs", return_value=0),
            patch("ingestion_worker.main.logger") as mock_logger,
        ):
            main.recover_stale_state()

        mock_logger.warning.assert_not_called()


class TestHeartbeat:
    def test_touch_heartbeat_creates_file(self, tmp_path):
        heartbeat_file = tmp_path / "heartbeat"
        with patch("ingestion_worker.heartbeat.settings.heartbeat_file", str(heartbeat_file)):
            from ingestion_worker.heartbeat import touch_heartbeat

            touch_heartbeat()

        assert heartbeat_file.exists()
