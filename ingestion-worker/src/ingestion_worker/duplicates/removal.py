"""The Statement Removal Handler (WR-65 to WR-67): carries out a removal the user confirmed.

The only code that deletes a statement, and the only way its embeddings are removed, because the
API Service never connects to the vector store (NFR-PD-4). The API writes a `queued` job; this
module executes it:

1. claim it, then **re-verify** it against what the user confirmed (WR-66);
2. in **one transaction** delete the statement and everything depending on it, remember the removed
   file as a `confirmed_duplicate`, mark the pair `removed`, and move the job to
   `embeddings_pending` with the removed transaction ids (WR-67, BR-46);
3. then delete the embeddings, with bounded retries.

If step 2 fails nothing is deleted. If step 3 fails only harmless orphaned vectors remain (a
similarity candidate is looked up by id, so a deleted transaction simply drops out).
"""

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session
from transactagent_db.models import (
    BankStatement,
    DuplicatePair,
    DuplicatePairStatus,
    KnownFileState,
    StatementRemovalJob,
    StatementRemovalJobStatus,
)

from ingestion_worker.duplicates import repository
from ingestion_worker.duplicates.cascade import delete_statements
from ingestion_worker.embedding import vector_store

logger = logging.getLogger(__name__)

EMBEDDING_ATTEMPTS = 5
EMBEDDING_WAITS_SECONDS = (1, 2, 4, 8)  # between attempts: four waits for five attempts

_S = StatementRemovalJobStatus


@dataclass
class RemovalResult:
    status: str  # "completed" | "failed" | "embeddings_failed"
    deleted_counts: dict[str, int] = field(default_factory=dict)
    reason: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def is_removal_pending_now(db: Session) -> bool:
    """A job is queued, or one has had its rows removed and is awaiting embedding cleanup."""
    return db.scalar(
        select(StatementRemovalJob.id).where(StatementRemovalJob.status.in_([_S.QUEUED, _S.EMBEDDINGS_PENDING])).limit(1)
    ) is not None


def fail_stale_removal_jobs(db: Session) -> int:
    """Startup recovery: a job left `running` can only be orphaned. The deletion commits atomically
    with the move to `embeddings_pending`, so a job still `running` deleted nothing and is safely
    failed (the user can retry). A job in `embeddings_pending` is NOT touched: it is picked up again."""
    stale = db.scalars(select(StatementRemovalJob).where(StatementRemovalJob.status == _S.RUNNING)).all()
    for job in stale:
        _fail(job, "Interrupted by a worker restart; nothing was deleted.")
    db.flush()
    return len(stale)


def _fail(job: StatementRemovalJob, reason: str, status: StatementRemovalJobStatus = _S.FAILED) -> None:
    job.status = status
    job.failure_reason = reason
    job.finished_at = _now()


def _next_job(db: Session) -> StatementRemovalJob | None:
    job = db.scalar(
        select(StatementRemovalJob).where(StatementRemovalJob.status == _S.QUEUED).order_by(StatementRemovalJob.requested_at).limit(1)
    )
    if job is not None:
        return job
    return db.scalar(
        select(StatementRemovalJob)
        .where(StatementRemovalJob.status == _S.EMBEDDINGS_PENDING)
        .order_by(StatementRemovalJob.requested_at)
        .limit(1)
    )


def _reverify(db: Session, job: StatementRemovalJob, pair: DuplicatePair | None) -> tuple[str | None, str | None]:
    """WR-66. Returns (error, keep_hash): an error message, or None when it is safe to delete."""
    if pair is None:
        return "The duplicate pair no longer exists.", None
    if pair.status != DuplicatePairStatus.PENDING:
        return f"The pair is no longer pending (it is {pair.status.value}).", None
    if not pair.removal_allowed:
        return "Removal is not offered for this pair (the statements differ in size).", None
    if job.remove_statement_hash not in (pair.hash_a, pair.hash_b):
        return "The statement to remove is not part of this pair.", None
    keep_hash = pair.hash_b if job.remove_statement_hash == pair.hash_a else pair.hash_a
    held = repository.held_hashes(db)
    if job.remove_statement_hash not in held:
        return "The statement to remove no longer exists.", None
    if keep_hash not in held:
        return "The statement to keep no longer exists, so nothing was removed (the last copy is never deleted).", None
    if pair.keep_hash != keep_hash:
        return "The proposal changed since you confirmed (a different copy is now proposed to be kept). Please review again.", None
    corrections = repository.manual_correction_counts(db, [job.remove_statement_hash])[job.remove_statement_hash]
    if corrections > job.corrections_acknowledged:
        return (
            f"The manual corrections on this copy increased from {job.corrections_acknowledged} to {corrections} "
            "since you confirmed. Please review again.",
            None,
        )
    return None, keep_hash


def process_next_removal(db: Session, *, sleep: Callable[[float], None] = time.sleep) -> RemovalResult | None:
    """Process one job (WR-65, branch three of `poll_once`). Returns None when there is nothing to do."""
    job = _next_job(db)
    if job is None:
        return None

    if job.status == _S.QUEUED:
        job.status = _S.RUNNING
        job.started_at = _now()
        db.commit()  # claim: visible to the API as "running"

        pair = db.get(DuplicatePair, job.pair_id)
        error, keep_hash = _reverify(db, job, pair)
        if error is not None:
            logger.info("Removal job %s refused: %s", job.id, error)
            _fail(job, error)
            db.commit()
            return RemovalResult("failed", reason=error)

        try:
            # ONE transaction (a savepoint inside the session's, committed below): the deletion, the
            # remembered file, the pair, and the job's move to embeddings_pending stand or fall together.
            with db.begin_nested():
                statement = db.scalar(select(BankStatement).where(BankStatement.pdf_content_hash == job.remove_statement_hash))
                deleted = delete_statements(db, [str(statement.id)])
                repository.insert_known_file(
                    db,
                    content_hash=job.remove_statement_hash,
                    state=KnownFileState.CONFIRMED_DUPLICATE,
                    matched_hash=keep_hash,
                    comparison_id=pair.comparison_id,
                )
                pair.status = DuplicatePairStatus.REMOVED
                pair.decided_at = _now()
                job.status = _S.EMBEDDINGS_PENDING
                job.removed_transaction_ids = [uuid.UUID(i) for i in deleted.transaction_ids]
                job.deleted_counts = deleted.counts
            db.commit()
        except Exception as exc:
            logger.exception("Removal job %s failed; nothing was deleted", job.id)
            db.expire_all()
            job = db.get(StatementRemovalJob, job.id)
            _fail(job, f"The removal could not be completed and nothing was deleted: {exc}")
            db.commit()
            return RemovalResult("failed", reason=job.failure_reason)
        logger.info("Removal job %s: deleted statement %s (%s)", job.id, job.remove_statement_hash[:8], job.deleted_counts)

    return _cleanup_embeddings(db, job, sleep)


def _cleanup_embeddings(db: Session, job: StatementRemovalJob, sleep: Callable[[float], None]) -> RemovalResult:
    """WR-67: up to five attempts in one poll cycle, waiting 1, 2, 4 and 8 seconds, each counted. A
    job resumed after a restart only has the attempts it has left."""
    ids = [str(i) for i in (job.removed_transaction_ids or [])]
    remaining = max(1, EMBEDDING_ATTEMPTS - job.embedding_attempts)
    for attempt in range(remaining):
        job.embedding_attempts += 1
        if vector_store.delete_embeddings(vector_store.TRANSACTIONS_COLLECTION, ids):
            job.status = _S.COMPLETED
            job.finished_at = _now()
            db.commit()
            return RemovalResult("completed", deleted_counts=dict(job.deleted_counts or {}))
        db.commit()  # record the attempt
        if attempt < remaining - 1:
            sleep(EMBEDDING_WAITS_SECONDS[min(job.embedding_attempts - 1, len(EMBEDDING_WAITS_SECONDS) - 1)])
    reason = (
        f"The statement was removed, but its search embeddings could not be deleted after "
        f"{job.embedding_attempts} attempts. Only unused search data remains; it is harmless."
    )
    _fail(job, reason, status=_S.EMBEDDINGS_FAILED)
    db.commit()
    logger.warning("Removal job %s: %s", job.id, reason)
    return RemovalResult("embeddings_failed", deleted_counts=dict(job.deleted_counts or {}), reason=reason)
