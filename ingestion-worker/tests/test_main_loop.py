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
        ):
            main.poll_once()

        mock_process_run.assert_not_called()
        mock_process_job.assert_not_called()


class TestHeartbeat:
    def test_touch_heartbeat_creates_file(self, tmp_path):
        heartbeat_file = tmp_path / "heartbeat"
        with patch("ingestion_worker.heartbeat.settings.heartbeat_file", str(heartbeat_file)):
            from ingestion_worker.heartbeat import touch_heartbeat

            touch_heartbeat()

        assert heartbeat_file.exists()
