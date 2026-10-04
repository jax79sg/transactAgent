"""Tests for main.py's poll_once() dispatch logic (WR-8: one run OR one job per
cycle, never both, never two of the same). session_scope and the repository/pipeline
calls are mocked -- the pipeline's own logic is already covered by
test_orchestrator_pipeline.py; this file only tests the dispatch wiring.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from ingestion_worker import main


@contextmanager
def _fake_session_scope(fake_db):
    yield fake_db


@pytest.fixture(autouse=True)
def _no_duplicate_work_by_default():
    """Epic 14 added two branches (removal, third; pair scan, sixth). The existing tests here are
    about the OTHER branches' dispatch, so by default those two find nothing to do; the new tests
    below override them. Without this, a MagicMock session would look like a pending removal."""
    with (
        patch("ingestion_worker.main.removal_service.is_removal_pending_now", return_value=False),
        patch("ingestion_worker.main.removal_service.fail_stale_removal_jobs", return_value=0),
        patch("ingestion_worker.main.duplicates_service.is_pair_scan_due_now", return_value=False),
    ):
        yield


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


class TestDuplicateBranches:
    """Epic 14, WR-65: the removal branch is third and the pair scan sixth, one thing per cycle."""

    def _scope(self, fake_db):
        return patch("ingestion_worker.main.session_scope", side_effect=lambda: _fake_session_scope(fake_db))

    def _quiet(self):
        """Every branch ahead of the one under test finds nothing."""
        return (
            patch("ingestion_worker.main.repository.find_queued_run", return_value=None),
            patch("ingestion_worker.main.repository.find_queued_recategorize_job", return_value=None),
        )

    def test_a_pending_removal_is_processed_when_no_run_or_job_is_queued(self):
        fake_db = MagicMock()
        quiet_run, quiet_job = self._quiet()
        with (
            self._scope(fake_db), quiet_run, quiet_job,
            patch("ingestion_worker.main.removal_service.is_removal_pending_now", return_value=True),
            patch("ingestion_worker.main.removal_service.process_next_removal") as mock_removal,
            patch("ingestion_worker.main.backup_service.is_backup_due_now") as mock_backup_due,
        ):
            main.poll_once()

        mock_removal.assert_called_once_with(fake_db)
        mock_backup_due.assert_not_called()  # one thing per cycle

    def test_a_pending_removal_wins_over_a_due_backup(self):
        fake_db = MagicMock()
        quiet_run, quiet_job = self._quiet()
        with (
            self._scope(fake_db), quiet_run, quiet_job,
            patch("ingestion_worker.main.removal_service.is_removal_pending_now", return_value=True),
            patch("ingestion_worker.main.removal_service.process_next_removal"),
            patch("ingestion_worker.main.backup_service.is_backup_due_now", return_value=True),
            patch("ingestion_worker.main.backup_service.run_backup") as mock_run_backup,
        ):
            main.poll_once()

        mock_run_backup.assert_not_called()

    def test_a_queued_run_wins_over_a_pending_removal(self):
        fake_db = MagicMock()
        fake_run = MagicMock()
        with (
            self._scope(fake_db),
            patch("ingestion_worker.main.repository.find_queued_run", return_value=fake_run),
            patch("ingestion_worker.main.repository.claim_run"),
            patch("ingestion_worker.main.pipeline.process_run"),
            patch.object(fake_db, "merge", return_value=fake_run),
            patch("ingestion_worker.main.removal_service.is_removal_pending_now", return_value=True) as mock_pending,
        ):
            main.poll_once()

        mock_pending.assert_not_called()

    def test_a_failing_removal_never_raises_out_of_the_cycle_and_does_not_starve_the_rest(self):
        fake_db = MagicMock()
        quiet_run, quiet_job = self._quiet()
        with (
            self._scope(fake_db), quiet_run, quiet_job,
            patch("ingestion_worker.main.removal_service.is_removal_pending_now", return_value=True),
            patch("ingestion_worker.main.removal_service.process_next_removal", side_effect=RuntimeError("boom")),
            patch("ingestion_worker.main.backup_service.is_backup_due_now", return_value=True),
            patch("ingestion_worker.main.backup_service.run_backup") as mock_run_backup,
            patch("ingestion_worker.main.logger") as mock_logger,
        ):
            main.poll_once()  # must not raise

        mock_logger.exception.assert_called_once()
        mock_run_backup.assert_called_once()  # the cycle carried on to the next branch

    def test_the_pair_scan_runs_only_when_nothing_earlier_did_and_is_due(self):
        fake_db = MagicMock()
        quiet_run, quiet_job = self._quiet()
        with (
            self._scope(fake_db), quiet_run, quiet_job,
            patch("ingestion_worker.main.backup_service.is_backup_due_now", return_value=False),
            patch("ingestion_worker.main.recurring_payments_service.is_detection_scan_due_now", return_value=False),
            patch("ingestion_worker.main.duplicates_service.is_pair_scan_due_now", return_value=True),
            patch("ingestion_worker.main.duplicates_service.run_pair_scan") as mock_scan,
            patch("ingestion_worker.main.embedding_service.process_next_embedding_batch") as mock_embed,
        ):
            main.poll_once()

        mock_scan.assert_called_once_with(fake_db)
        mock_embed.assert_not_called()  # the scan ran, so the embedding backlog waits for the next cycle

    def test_the_pair_scan_comes_before_the_embedding_backlog_so_the_backlog_cannot_starve_it(self):
        fake_db = MagicMock()
        quiet_run, quiet_job = self._quiet()
        order = []
        with (
            self._scope(fake_db), quiet_run, quiet_job,
            patch("ingestion_worker.main.backup_service.is_backup_due_now", return_value=False),
            patch("ingestion_worker.main.recurring_payments_service.is_detection_scan_due_now", return_value=False),
            patch("ingestion_worker.main.duplicates_service.is_pair_scan_due_now", return_value=True),
            patch("ingestion_worker.main.duplicates_service.run_pair_scan", side_effect=lambda _db: order.append("scan")),
            patch("ingestion_worker.main.embedding_service.process_next_embedding_batch", side_effect=lambda _db: order.append("embed")),
        ):
            main.poll_once()

        assert order == ["scan"]

    def test_the_pair_scan_is_not_run_after_a_detection_scan(self):
        fake_db = MagicMock()
        quiet_run, quiet_job = self._quiet()
        with (
            self._scope(fake_db), quiet_run, quiet_job,
            patch("ingestion_worker.main.backup_service.is_backup_due_now", return_value=False),
            patch("ingestion_worker.main.recurring_payments_service.is_detection_scan_due_now", return_value=True),
            patch("ingestion_worker.main.recurring_payments_service.run_detection_scan"),
            patch("ingestion_worker.main.duplicates_service.is_pair_scan_due_now", return_value=True) as mock_due,
        ):
            main.poll_once()

        mock_due.assert_not_called()

    def test_a_failing_pair_scan_is_logged_and_never_raises(self):
        fake_db = MagicMock()
        quiet_run, quiet_job = self._quiet()
        with (
            self._scope(fake_db), quiet_run, quiet_job,
            patch("ingestion_worker.main.backup_service.is_backup_due_now", return_value=False),
            patch("ingestion_worker.main.recurring_payments_service.is_detection_scan_due_now", return_value=False),
            patch("ingestion_worker.main.duplicates_service.is_pair_scan_due_now", return_value=True),
            patch("ingestion_worker.main.duplicates_service.run_pair_scan", side_effect=RuntimeError("boom")),
            patch("ingestion_worker.main.embedding_service.process_next_embedding_batch") as mock_embed,
            patch("ingestion_worker.main.logger") as mock_logger,
        ):
            main.poll_once()  # must not raise

        mock_logger.exception.assert_called_once()
        mock_embed.assert_called_once()  # a failed scan does not starve the embedding backlog


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

    def test_stale_removal_jobs_are_failed_at_startup_and_reported(self):
        fake_db = MagicMock()
        with (
            patch("ingestion_worker.main.session_scope", side_effect=lambda: _fake_session_scope(fake_db)),
            patch("ingestion_worker.main.repository.fail_stale_runs", return_value=0),
            patch("ingestion_worker.main.repository.fail_stale_recategorize_jobs", return_value=0),
            patch("ingestion_worker.main.removal_service.fail_stale_removal_jobs", return_value=2) as mock_fail_removals,
            patch("ingestion_worker.main.logger") as mock_logger,
        ):
            main.recover_stale_state()

        mock_fail_removals.assert_called_once_with(fake_db)
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
