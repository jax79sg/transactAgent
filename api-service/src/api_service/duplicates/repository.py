"""Duplicate Review queries (Epic 14). Statements are found by content hash, never by a stored row id
(BR-50). Everything here is read-only except the small writes the service asks for explicitly."""

from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload
from transactagent_db.models import (
    BankStatement,
    CategorySource,
    DuplicateComparison,
    DuplicatePair,
    DuplicatePairStatus,
    DuplicateScanState,
    KnownFile,
    StatementRemovalJob,
    StatementRemovalJobStatus,
    Transaction,
)

ACTIVE_JOB_STATUSES = (
    StatementRemovalJobStatus.QUEUED,
    StatementRemovalJobStatus.RUNNING,
    StatementRemovalJobStatus.EMBEDDINGS_PENDING,
)

# The kinds of row a removal deletes besides the statement's own transactions and sections (BR-51).
# A test ties this list to the real table metadata so a new dependent table cannot be missed here.
PREVIEW_DEPENDENT_KINDS = (
    "recategorization_jobs",
    "recategorization_proposals",
    "categorization_disagreements",
    "recurring_payment_matches",
)

_IDS = "CAST(:ids AS uuid[])"
_TXN_IDS = f"(SELECT id FROM transactions WHERE bank_statement_id = ANY({_IDS}))"
_JOB_IDS = f"(SELECT id FROM recategorization_jobs WHERE source_transaction_id IN {_TXN_IDS})"


def get_pair(db: Session, pair_id) -> DuplicatePair | None:
    return db.get(DuplicatePair, pair_id)


def get_comparison(db: Session, comparison_id) -> DuplicateComparison | None:
    return db.scalar(
        select(DuplicateComparison).where(DuplicateComparison.id == comparison_id).options(selectinload(DuplicateComparison.rows))
    )


def latest_job(db: Session, pair_id) -> StatementRemovalJob | None:
    return db.scalar(
        select(StatementRemovalJob)
        .where(StatementRemovalJob.pair_id == pair_id)
        .order_by(StatementRemovalJob.requested_at.desc(), StatementRemovalJob.id.desc())
        .limit(1)
    )


def has_active_job(db: Session, pair_id) -> bool:
    return db.scalar(
        select(StatementRemovalJob.id)
        .where(StatementRemovalJob.pair_id == pair_id, StatementRemovalJob.status.in_(ACTIVE_JOB_STATUSES))
        .limit(1)
    ) is not None


def list_candidate_pairs(db: Session, removed_since: datetime) -> list[DuplicatePair]:
    """Pairs the panel may show (AR-39): every pending pair, every pair with a removal in flight, and
    pairs removed since `removed_since`. The service groups and orders them."""
    active_pair_ids = select(StatementRemovalJob.pair_id).where(StatementRemovalJob.status.in_(ACTIVE_JOB_STATUSES))
    return list(
        db.scalars(
            select(DuplicatePair).where(
                (DuplicatePair.status == DuplicatePairStatus.PENDING)
                | (DuplicatePair.id.in_(active_pair_ids))
                | ((DuplicatePair.status == DuplicatePairStatus.REMOVED) & (DuplicatePair.decided_at >= removed_since))
            )
        )
    )


def count_pending_without_active_job(db: Session) -> int:
    active_pair_ids = select(StatementRemovalJob.pair_id).where(StatementRemovalJob.status.in_(ACTIVE_JOB_STATUSES))
    return db.scalar(
        select(func.count(DuplicatePair.id)).where(
            DuplicatePair.status == DuplicatePairStatus.PENDING, DuplicatePair.id.not_in(active_pair_ids)
        )
    )


def count_pending(db: Session) -> int:
    """Pairs flagged and not yet decided, in-flight ones included (they stay pending until the deletion commits)."""
    return db.scalar(select(func.count(DuplicatePair.id)).where(DuplicatePair.status == DuplicatePairStatus.PENDING))


def statement_ids_by_hash(db: Session, hashes: list[str]) -> dict[str, object]:
    rows = db.execute(select(BankStatement.pdf_content_hash, BankStatement.id).where(BankStatement.pdf_content_hash.in_(hashes)))
    return dict(rows.all())


def statement_exists(db: Session, content_hash: str) -> bool:
    return db.scalar(select(BankStatement.id).where(BankStatement.pdf_content_hash == content_hash)) is not None


def manual_corrections(db: Session, statement_id) -> int:
    return db.scalar(
        select(func.count(Transaction.id)).where(
            Transaction.bank_statement_id == statement_id, Transaction.category_source == CategorySource.MANUAL
        )
    )


def preview_counts(db: Session, statement_id) -> dict[str, int]:
    """What deleting this one statement would delete: the same predicates the worker's delete helper uses."""
    params = {"ids": [str(statement_id)]}

    def count(sql: str) -> int:
        return db.execute(text(sql), params).scalar_one()

    return {
        "transactions": count(f"SELECT count(*) FROM transactions WHERE bank_statement_id = ANY({_IDS})"),
        "statement_sections": count(f"SELECT count(*) FROM statement_accounts WHERE bank_statement_id = ANY({_IDS})"),
        "recategorization_jobs": count(f"SELECT count(*) FROM recategorization_jobs WHERE source_transaction_id IN {_TXN_IDS}"),
        "recategorization_proposals": count(
            f"SELECT count(*) FROM recategorization_proposals WHERE candidate_transaction_id IN {_TXN_IDS} "
            f"OR recategorization_job_id IN {_JOB_IDS}"
        ),
        "categorization_disagreements": count(f"SELECT count(*) FROM categorization_disagreements WHERE transaction_id IN {_TXN_IDS}"),
        "recurring_payment_matches": count(f"SELECT count(*) FROM recurring_payment_matches WHERE transaction_id IN {_TXN_IDS}"),
    }


def known_files_for_comparison(db: Session, comparison_id) -> list[KnownFile]:
    return list(db.scalars(select(KnownFile).where(KnownFile.comparison_id == comparison_id).order_by(KnownFile.created_at)))


def pair_for_comparison(db: Session, comparison_id) -> DuplicatePair | None:
    return db.scalar(select(DuplicatePair).where(DuplicatePair.comparison_id == comparison_id).order_by(DuplicatePair.found_at).limit(1))


def get_scan_state(db: Session) -> DuplicateScanState | None:
    return db.get(DuplicateScanState, 1)


def get_or_create_scan_state(db: Session) -> DuplicateScanState:
    state = get_scan_state(db)
    if state is None:
        state = DuplicateScanState(id=1)
        db.add(state)
        db.flush()
    return state
