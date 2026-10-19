"""WR-65..WR-67: the Statement Removal Handler. Real PostgreSQL; the vector store is mocked at the
module boundary (a real Qdrant is exercised in Build and Test)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from duplicates_helpers import june, make_statement
from sqlalchemy import select
from transactagent_db.models import (
    BankStatement,
    DuplicatePairStatus,
    IngestionRunFile,
    KnownFile,
    KnownFileState,
    StatementRemovalJob,
    StatementRemovalJobStatus,
    Transaction,
)

from ingestion_worker import config
from ingestion_worker.duplicates import removal, repository, service

H1, H2 = "1" * 64, "2" * 64
S = StatementRemovalJobStatus
DELETE = "ingestion_worker.duplicates.removal.vector_store.delete_embeddings"


@pytest.fixture
def pair_of_copies(db_session, monkeypatch):
    """The UOB shape: two copies of June, the earlier one carrying 2 manual corrections (so it is kept)."""
    monkeypatch.setattr(config.settings, "duplicate_detection_enabled", True)
    keep = make_statement(db_session, h=H1, rows=june(5), manual=2, ingested_days=0, file_name="first.pdf")
    remove = make_statement(db_session, h=H2, rows=june(5), ingested_days=30, file_name="second.pdf")
    service.run_pair_scan(db_session)
    pair = repository.load_pairs(db_session)[(H1, H2)]
    assert pair.keep_hash == H1
    return pair, keep, remove


def request(db, pair, *, remove_hash=H2, acknowledged=0):
    job = StatementRemovalJob(pair_id=pair.id, remove_statement_hash=remove_hash, corrections_acknowledged=acknowledged)
    db.add(job)
    db.flush()
    return job


def no_sleep(_seconds):
    pass


class TestHappyPath:
    def test_removes_the_copy_its_dependents_and_its_embeddings(self, db_session, pair_of_copies):
        pair, keep, remove = pair_of_copies
        remove_txn_ids = sorted(str(t.id) for t in db_session.query(Transaction).filter_by(bank_statement_id=remove.id))
        job = request(db_session, pair)

        with patch(DELETE, return_value=True) as delete:
            result = removal.process_next_removal(db_session, sleep=no_sleep)

        assert result.status == "completed" and result.deleted_counts["transactions"] == 5
        delete.assert_called_once()
        assert sorted(delete.call_args.args[1]) == remove_txn_ids  # the right ids, from before the delete
        assert db_session.scalar(select(BankStatement).where(BankStatement.pdf_content_hash == H2)) is None
        assert db_session.scalar(select(BankStatement).where(BankStatement.pdf_content_hash == H1)) is not None
        assert db_session.query(Transaction).filter_by(bank_statement_id=keep.id).count() == 5  # the kept copy is intact
        db_session.refresh(job)
        assert job.status is S.COMPLETED and job.finished_at is not None and job.embedding_attempts == 1
        assert [str(i) for i in job.removed_transaction_ids] == remove_txn_ids or sorted(map(str, job.removed_transaction_ids)) == remove_txn_ids

    def test_the_removed_file_is_remembered_and_the_pair_is_removed(self, db_session, pair_of_copies):
        pair, _keep, _remove = pair_of_copies
        request(db_session, pair)

        with patch(DELETE, return_value=True):
            removal.process_next_removal(db_session, sleep=no_sleep)

        known = repository.get_known_file(db_session, H2)
        assert known.state is KnownFileState.CONFIRMED_DUPLICATE
        assert known.matched_statement_hash == H1 and known.comparison_id == pair.comparison_id
        db_session.refresh(pair)
        assert pair.status is DuplicatePairStatus.REMOVED and pair.decided_at is not None

    def test_the_removed_copys_run_file_survives_detached(self, db_session, pair_of_copies):
        pair, _keep, _remove = pair_of_copies
        request(db_session, pair)

        with patch(DELETE, return_value=True):
            removal.process_next_removal(db_session, sleep=no_sleep)

        run_file = db_session.query(IngestionRunFile).filter_by(drive_file_name="second.pdf").one()
        assert run_file.bank_statement_id is None

    def test_nothing_to_do_returns_none(self, db_session):
        assert removal.process_next_removal(db_session, sleep=no_sleep) is None
        assert removal.is_removal_pending_now(db_session) is False

    def test_a_queued_job_is_pending(self, db_session, pair_of_copies):
        request(db_session, pair_of_copies[0])
        assert removal.is_removal_pending_now(db_session) is True


class TestReverification:
    """WR-66: every refusal leaves everything untouched and the job failed with a reason; the pair stays pending."""

    def _assert_untouched(self, db, pair, job, reason_fragment):
        db.refresh(job)
        db.refresh(pair)
        assert job.status is S.FAILED and reason_fragment in job.failure_reason and job.finished_at is not None
        assert pair.status is DuplicatePairStatus.PENDING
        assert db.query(BankStatement).count() == 2
        assert repository.get_known_file(db, H2) is None

    def test_pair_no_longer_pending(self, db_session, pair_of_copies):
        pair, *_ = pair_of_copies
        pair.status = DuplicatePairStatus.DISMISSED
        job = request(db_session, pair)

        with patch(DELETE, return_value=True) as delete:
            result = removal.process_next_removal(db_session, sleep=no_sleep)

        assert result.status == "failed"
        delete.assert_not_called()
        db_session.refresh(job)
        assert job.status is S.FAILED and "no longer pending" in job.failure_reason
        assert db_session.query(BankStatement).count() == 2

    def test_removal_not_allowed(self, db_session, pair_of_copies):
        pair, *_ = pair_of_copies
        pair.removal_allowed = False
        job = request(db_session, pair)

        with patch(DELETE, return_value=True):
            removal.process_next_removal(db_session, sleep=no_sleep)

        self._assert_untouched(db_session, pair, job, "not offered")

    def test_the_statement_to_remove_is_gone(self, db_session, pair_of_copies):
        pair, _keep, remove = pair_of_copies
        db_session.query(Transaction).filter_by(bank_statement_id=remove.id).delete()
        db_session.query(IngestionRunFile).delete()
        db_session.delete(remove)
        db_session.flush()
        job = request(db_session, pair)

        with patch(DELETE, return_value=True):
            removal.process_next_removal(db_session, sleep=no_sleep)

        db_session.refresh(job)
        assert job.status is S.FAILED and "no longer exists" in job.failure_reason
        assert db_session.query(BankStatement).count() == 1

    def test_the_statement_to_keep_is_gone_so_the_last_copy_is_never_deleted(self, db_session, pair_of_copies):
        pair, keep, remove = pair_of_copies
        db_session.query(Transaction).filter_by(bank_statement_id=keep.id).delete()
        db_session.query(IngestionRunFile).filter_by(bank_statement_id=keep.id).delete()
        db_session.delete(keep)
        db_session.flush()
        job = request(db_session, pair)

        with patch(DELETE, return_value=True) as delete:
            removal.process_next_removal(db_session, sleep=no_sleep)

        delete.assert_not_called()
        db_session.refresh(job)
        assert job.status is S.FAILED and "last copy is never deleted" in job.failure_reason
        assert db_session.query(Transaction).filter_by(bank_statement_id=remove.id).count() == 5

    def test_the_proposal_changed_since_the_user_confirmed(self, db_session, pair_of_copies):
        pair, *_ = pair_of_copies
        job = request(db_session, pair)
        pair.keep_hash = H2  # a re-scan now proposes keeping the OTHER copy

        with patch(DELETE, return_value=True):
            removal.process_next_removal(db_session, sleep=no_sleep)

        self._assert_untouched(db_session, pair, job, "proposal changed")

    def test_the_corrections_on_the_removed_copy_increased(self, db_session, pair_of_copies):
        pair, _keep, remove = pair_of_copies
        job = request(db_session, pair, acknowledged=0)
        first = db_session.query(Transaction).filter_by(bank_statement_id=remove.id).first()
        first.category_source = repository.CategorySource.MANUAL  # the user corrected one after confirming
        db_session.flush()

        with patch(DELETE, return_value=True):
            removal.process_next_removal(db_session, sleep=no_sleep)

        self._assert_untouched(db_session, pair, job, "increased from 0 to 1")

    def test_corrections_at_or_below_the_acknowledged_count_are_fine(self, db_session, pair_of_copies):
        pair, _keep, remove = pair_of_copies
        first = db_session.query(Transaction).filter_by(bank_statement_id=remove.id).first()
        first.category_source = repository.CategorySource.MANUAL
        db_session.flush()
        request(db_session, pair, acknowledged=1)

        with patch(DELETE, return_value=True):
            result = removal.process_next_removal(db_session, sleep=no_sleep)

        assert result.status == "completed"

    def test_the_hash_to_remove_must_belong_to_the_pair(self, db_session, pair_of_copies):
        pair, *_ = pair_of_copies
        job = request(db_session, pair, remove_hash="9" * 64)

        with patch(DELETE, return_value=True):
            removal.process_next_removal(db_session, sleep=no_sleep)

        db_session.refresh(job)
        assert job.status is S.FAILED and "not part of this pair" in job.failure_reason


class TestAtomicity:
    def test_a_failure_during_the_delete_transaction_leaves_nothing_deleted(self, db_session, pair_of_copies):
        """The deletion, the remembered file, the pair and the job move are one transaction: if the
        bookkeeping fails AFTER the rows were deleted, the deletion is rolled back too."""
        pair, _keep, remove = pair_of_copies
        job = request(db_session, pair)

        with (
            patch.object(repository, "insert_known_file", side_effect=RuntimeError("boom")),
            patch(DELETE, return_value=True) as delete,
        ):
            result = removal.process_next_removal(db_session, sleep=no_sleep)

        assert result.status == "failed" and "nothing was deleted" in result.reason
        delete.assert_not_called()  # no embeddings were deleted for rows that still exist
        assert db_session.query(Transaction).filter_by(bank_statement_id=remove.id).count() == 5
        assert db_session.query(BankStatement).count() == 2
        db_session.refresh(job)
        db_session.refresh(pair)
        assert job.status is S.FAILED and job.removed_transaction_ids is None
        assert pair.status is DuplicatePairStatus.PENDING
        assert db_session.query(KnownFile).count() == 0


class TestEmbeddingCleanup:
    def test_fails_once_then_succeeds(self, db_session, pair_of_copies):
        job = request(db_session, pair_of_copies[0])
        waits = []

        with patch(DELETE, side_effect=[False, True]):
            result = removal.process_next_removal(db_session, sleep=waits.append)

        assert result.status == "completed" and waits == [1]
        db_session.refresh(job)
        assert job.status is S.COMPLETED and job.embedding_attempts == 2

    def test_five_failures_park_the_job_with_the_data_deleted(self, db_session, pair_of_copies):
        pair, *_ = pair_of_copies
        job = request(db_session, pair)
        waits = []

        with patch(DELETE, return_value=False) as delete:
            result = removal.process_next_removal(db_session, sleep=waits.append)

        assert result.status == "embeddings_failed"
        assert delete.call_count == 5 and waits == [1, 2, 4, 8]
        db_session.refresh(job)
        db_session.refresh(pair)
        assert job.status is S.EMBEDDINGS_FAILED and "harmless" in job.failure_reason and job.embedding_attempts == 5
        assert pair.status is DuplicatePairStatus.REMOVED  # the statement IS gone
        assert db_session.query(BankStatement).filter_by(pdf_content_hash=H2).count() == 0
        assert removal.is_removal_pending_now(db_session) is False  # parked: it no longer blocks the poll loop

    def test_a_job_awaiting_embedding_cleanup_resumes_with_the_attempts_it_has_left(self, db_session, pair_of_copies):
        pair, *_ = pair_of_copies
        job = request(db_session, pair)
        job.status = S.EMBEDDINGS_PENDING
        job.removed_transaction_ids = [uuid.uuid4()]
        job.embedding_attempts = 3
        db_session.flush()

        with patch(DELETE, return_value=False) as delete:
            result = removal.process_next_removal(db_session, sleep=no_sleep)

        assert result.status == "embeddings_failed" and delete.call_count == 2  # 5 - 3 attempts left

    def test_a_resumed_job_that_succeeds_completes(self, db_session, pair_of_copies):
        pair, *_ = pair_of_copies
        job = request(db_session, pair)
        job.status = S.EMBEDDINGS_PENDING
        job.removed_transaction_ids = [uuid.uuid4()]
        db_session.flush()

        with patch(DELETE, return_value=True):
            result = removal.process_next_removal(db_session, sleep=no_sleep)

        assert result.status == "completed"


class TestOrderingAndRecovery:
    def test_queued_jobs_run_before_jobs_awaiting_cleanup_and_oldest_first(self, db_session, pair_of_copies):
        """Two pairs (BR-45 allows one active job per pair): a job awaiting cleanup is older, a
        queued job newer, and the queued one is taken first; with only waiting jobs, oldest first."""
        first_pair, *_ = pair_of_copies
        make_statement(db_session, h="3" * 64, rows=june(5), ingested_days=40)
        service.run_pair_scan(db_session)
        pairs = repository.load_pairs(db_session)
        second_pair = pairs[(H1, "3" * 64)]

        waiting = request(db_session, first_pair)
        waiting.status = S.EMBEDDINGS_PENDING
        waiting.removed_transaction_ids = [uuid.uuid4()]
        waiting.requested_at = datetime(2026, 1, 1, tzinfo=UTC)
        queued = request(db_session, second_pair, remove_hash="3" * 64)
        queued.requested_at = datetime(2026, 2, 1, tzinfo=UTC)
        db_session.flush()

        assert removal._next_job(db_session).id == queued.id

        queued.status = S.COMPLETED
        db_session.flush()
        assert removal._next_job(db_session).id == waiting.id

    def test_a_stale_running_job_is_failed_at_startup_and_a_waiting_one_is_not(self, db_session, pair_of_copies):
        pair, *_ = pair_of_copies
        running = request(db_session, pair)
        running.status = S.RUNNING
        db_session.flush()
        assert removal.fail_stale_removal_jobs(db_session) == 1
        db_session.refresh(running)
        assert running.status is S.FAILED and "nothing was deleted" in running.failure_reason

        waiting = request(db_session, pair)
        waiting.status = S.EMBEDDINGS_PENDING
        waiting.removed_transaction_ids = [uuid.uuid4()]
        db_session.flush()
        assert removal.fail_stale_removal_jobs(db_session) == 0
        db_session.refresh(waiting)
        assert waiting.status is S.EMBEDDINGS_PENDING
