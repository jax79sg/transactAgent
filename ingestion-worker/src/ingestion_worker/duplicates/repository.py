"""Persistence for probable-duplicate detection (WR-59, WR-63): loading held statements as
matcher inputs, and the remembered files, comparisons, pairs and scan state.

Statements are identified by content hash throughout (BR-50): nothing here keeps a row id of a
statement across calls.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from transactagent_db.models import (
    AccountKey,
    BankStatement,
    CategorySource,
    ComparisonRowMarker,
    ComparisonSide,
    DuplicateComparison,
    DuplicateComparisonRow,
    DuplicatePair,
    DuplicatePairStatus,
    DuplicateScanState,
    IngestionRunFile,
    IngestionRunFileOutcome,
    KnownFile,
    KnownFileState,
    StatementAccount,
    StatementRemovalJob,
    StatementRemovalJobStatus,
    Transaction,
)

from ingestion_worker.accounts.normalize import bank_key
from ingestion_worker.duplicates.matching import AccountFact, StatementSide, TxnKey

ACTIVE_JOB_STATUSES = (
    StatementRemovalJobStatus.QUEUED,
    StatementRemovalJobStatus.RUNNING,
    StatementRemovalJobStatus.EMBEDDINGS_PENDING,
)


@dataclass(frozen=True)
class HeldSummary:
    """A held statement without its transactions: enough to choose candidates cheaply."""

    statement_id: object
    content_hash: str
    bank_name: str | None
    bank_key: str
    ingested_at: datetime
    period: tuple[date, date] | None
    transaction_count: int


def load_summaries(db: Session) -> list[HeldSummary]:
    rows = db.execute(
        select(
            BankStatement.id,
            BankStatement.pdf_content_hash,
            BankStatement.bank_name,
            BankStatement.processed_at,
            func.min(Transaction.transaction_date),
            func.max(Transaction.transaction_date),
            func.count(Transaction.id),
        )
        .outerjoin(Transaction, Transaction.bank_statement_id == BankStatement.id)
        .group_by(BankStatement.id)
        .order_by(BankStatement.processed_at, BankStatement.pdf_content_hash)
    ).all()
    return [
        HeldSummary(
            statement_id=r[0],
            content_hash=r[1],
            bank_name=r[2],
            bank_key=bank_key(r[2]) if r[2] else "",
            ingested_at=r[3],
            period=(r[4], r[5]) if r[4] is not None else None,
            transaction_count=r[6],
        )
        for r in rows
    ]


def load_sides(db: Session, summaries: list[HeldSummary]) -> list[StatementSide]:
    """Held statements as matcher inputs: transactions, the account facts of their sections
    (the section's account keys at the same bank key that carry an identifier, with the
    section's closing balance), and the file name from the run file that processed them."""
    if not summaries:
        return []
    ids = [s.statement_id for s in summaries]
    txns: dict[object, list[TxnKey]] = {s.statement_id: [] for s in summaries}
    for t in db.scalars(select(Transaction).where(Transaction.bank_statement_id.in_(ids)).order_by(Transaction.transaction_date, Transaction.id)):
        amount = t.out_flow if t.out_flow is not None else t.in_flow
        txns[t.bank_statement_id].append(
            TxnKey(t.transaction_date, Decimal(amount), "out" if t.out_flow is not None else "in", t.currency, t.description)
        )

    key_by_id = {s.statement_id: s.bank_key for s in summaries}
    facts: dict[object, list[AccountFact]] = {s.statement_id: [] for s in summaries}
    section_rows = db.execute(
        select(StatementAccount.bank_statement_id, AccountKey.account_identifier, AccountKey.currency,
               StatementAccount.closing_balance, StatementAccount.closing_balance_date, AccountKey.bank_key)
        .join(AccountKey, AccountKey.account_id == StatementAccount.account_id)
        .where(StatementAccount.bank_statement_id.in_(ids), AccountKey.account_identifier.is_not(None))
    ).all()
    for statement_id, identifier, currency, balance, balance_date, key in section_rows:
        if key == key_by_id[statement_id]:
            facts[statement_id].append(AccountFact(identifier, currency, balance, balance_date))

    file_names = {
        r[0]: r[1]
        for r in db.execute(
            select(IngestionRunFile.bank_statement_id, IngestionRunFile.drive_file_name)
            .where(IngestionRunFile.bank_statement_id.in_(ids), IngestionRunFile.outcome == IngestionRunFileOutcome.PROCESSED)
            .order_by(IngestionRunFile.processed_at)
        )
    }  # later rows win, so the most recent processing's file name is kept
    return [
        StatementSide(
            content_hash=s.content_hash,
            bank_key=s.bank_key,
            transactions=tuple(txns[s.statement_id]),
            accounts=tuple(facts[s.statement_id]),
            bank_name=s.bank_name,
            file_name=file_names.get(s.statement_id),
            ingested_at=s.ingested_at,
        )
        for s in summaries
    ]


def manual_correction_counts(db: Session, hashes: list[str]) -> dict[str, int]:
    """Manual category corrections per statement (by content hash)."""
    if not hashes:
        return {}
    rows = db.execute(
        select(BankStatement.pdf_content_hash, func.count(Transaction.id))
        .join(Transaction, Transaction.bank_statement_id == BankStatement.id)
        .where(BankStatement.pdf_content_hash.in_(hashes), Transaction.category_source == CategorySource.MANUAL)
        .group_by(BankStatement.pdf_content_hash)
    ).all()
    counts = dict.fromkeys(hashes, 0)
    counts.update(dict(rows))
    return counts


def held_hashes(db: Session) -> set[str]:
    return set(db.scalars(select(BankStatement.pdf_content_hash)))


# ---- remembered files -------------------------------------------------------------------------


def get_known_file(db: Session, content_hash: str) -> KnownFile | None:
    return db.scalar(select(KnownFile).where(KnownFile.pdf_content_hash == content_hash))


def overridden_hashes(db: Session) -> set[str]:
    return set(db.scalars(select(KnownFile.pdf_content_hash).where(KnownFile.state == KnownFileState.OVERRIDDEN)))


def insert_known_file(
    db: Session, *, content_hash: str, state: KnownFileState, matched_hash: str, comparison_id
) -> KnownFile:
    """Idempotent: a hash has at most one remembered record (BR-39), and an existing one is
    never overwritten here (BR-41: the only change after insertion is to `overridden`)."""
    existing = get_known_file(db, content_hash)
    if existing is not None:
        return existing
    row = KnownFile(
        pdf_content_hash=content_hash, state=state, matched_statement_hash=matched_hash, comparison_id=comparison_id
    )
    db.add(row)
    db.flush()
    return row


# ---- comparisons ------------------------------------------------------------------------------


def create_comparison(db: Session, draft) -> DuplicateComparison:
    """Write a comparison and its rows. `draft` is a duplicates.service.ComparisonDraft."""
    e, l_ = draft.earlier, draft.later
    comparison = DuplicateComparison(
        earlier_content_hash=e.content_hash,
        earlier_file_name=e.file_name,
        earlier_bank_name=e.bank_name,
        earlier_period_start=e.period_start,
        earlier_period_end=e.period_end,
        earlier_transaction_count=e.transaction_count,
        later_content_hash=l_.content_hash,
        later_file_name=l_.file_name,
        later_bank_name=l_.bank_name,
        later_period_start=l_.period_start,
        later_period_end=l_.period_end,
        later_transaction_count=l_.transaction_count,
        matched_count=draft.matched_count,
        match_ratio=draft.match_ratio,
        reason=draft.reason,
    )
    db.add(comparison)
    db.flush()
    for side_name, side in ((ComparisonSide.EARLIER, e), (ComparisonSide.LATER, l_)):
        for row in side.rows:
            db.add(
                DuplicateComparisonRow(
                    comparison_id=comparison.id,
                    side=side_name,
                    rank=row.rank,
                    transaction_date=row.date,
                    description=row.description,
                    out_flow=row.amount if row.direction == "out" else None,
                    in_flow=row.amount if row.direction == "in" else None,
                    currency=row.currency,
                    marker=ComparisonRowMarker(row.marker),
                )
            )
    db.flush()
    return comparison


# ---- pairs ------------------------------------------------------------------------------------


def pair_key(hash_one: str, hash_two: str) -> tuple[str, str]:
    """Canonical order (BR-43): the smaller hash first, in byte order like the database check."""
    return (hash_one, hash_two) if hash_one.encode() <= hash_two.encode() else (hash_two, hash_one)


def load_pairs(db: Session) -> dict[tuple[str, str], DuplicatePair]:
    return {(p.hash_a, p.hash_b): p for p in db.scalars(select(DuplicatePair))}


def dismissed_pair_keys(db: Session) -> set[tuple[str, str]]:
    return {
        (p.hash_a, p.hash_b)
        for p in db.scalars(select(DuplicatePair).where(DuplicatePair.status == DuplicatePairStatus.DISMISSED))
    }


def insert_pair(db: Session, *, key: tuple[str, str], comparison_id, keep_hash: str, removal_allowed: bool) -> DuplicatePair:
    pair = DuplicatePair(
        hash_a=key[0], hash_b=key[1], comparison_id=comparison_id, keep_hash=keep_hash, removal_allowed=removal_allowed
    )
    db.add(pair)
    db.flush()
    return pair


def supersede_pair(db: Session, pair: DuplicatePair) -> None:
    pair.status = DuplicatePairStatus.SUPERSEDED
    pair.decided_at = datetime.now(UTC)
    db.flush()


def has_active_removal_job(db: Session) -> bool:
    return db.scalar(select(func.count(StatementRemovalJob.id)).where(StatementRemovalJob.status.in_(ACTIVE_JOB_STATUSES))) > 0


# ---- scan state -------------------------------------------------------------------------------


def get_scan_state(db: Session) -> DuplicateScanState | None:
    return db.get(DuplicateScanState, 1)


def get_or_create_scan_state(db: Session) -> DuplicateScanState:
    state = get_scan_state(db)
    if state is None:
        state = DuplicateScanState(id=1)
        db.add(state)
        db.flush()
    return state


def latest_statement_time(db: Session) -> datetime | None:
    return db.scalar(select(func.max(BankStatement.processed_at)))
