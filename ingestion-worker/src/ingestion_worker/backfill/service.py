"""The Backfill Tool's `run` flow (WR-52..WR-55): wipe-and-reingest so every existing
statement gains accounts, account sections, and closing balances.

Safety rails, in order: pre-flight refusals -> dry run -> verified backup -> typed
confirmation -> single-transaction wipe -> vector-collection recreation -> reingest. Nothing
is ever wiped before the backup is verified AND the operator has typed the confirmation.
"""

import logging
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field

from sqlalchemy import Connection, text
from sqlalchemy.orm import Session
from transactagent_db.models import IngestionRun, IngestionRunStatus, User

from ingestion_worker.backfill import duplicates as backfill_duplicates
from ingestion_worker.backfill import export
from ingestion_worker.backfill.tables import BACKED_UP_TABLES
from ingestion_worker.clients import drive_client
from ingestion_worker.duplicates.cascade import (
    IDS_SQL,
    JOB_IDS_SQL,
    TXN_IDS_SQL,
    delete_statements,
)
from ingestion_worker.embedding import vector_store
from ingestion_worker.orchestrator import pipeline

logger = logging.getLogger(__name__)

# The wipe's SQL lives in duplicates/cascade.py (WR-68): one implementation shared with the
# Statement Removal Handler. The fragments are re-exported here under their original names
# because scoped_counts below counts over the same set.
_IDS = IDS_SQL
_TXN_IDS = TXN_IDS_SQL
_JOB_IDS = JOB_IDS_SQL


class BackfillRefused(Exception):
    """A pre-flight check or confirmation failed. Nothing has been changed."""


@dataclass
class WipeSet:
    statement_ids: list[str] = field(default_factory=list)
    kept_missing_pdf: list[dict] = field(default_factory=list)
    already_converted: int = 0


@dataclass
class DryRun:
    wipe_set: WipeSet
    counts: dict[str, int]
    drive_pdf_count: int
    # Epic 14 (FR-PD-15): which copy of each probable-duplicate pair the reingest will skip.
    skip_plan: backfill_duplicates.SkipPlan = field(default_factory=backfill_duplicates.SkipPlan)


def compute_wipe_set(db: Session, drive_file_ids: set[str]) -> WipeSet:
    """WR-53: a statement is wiped only if it has NO account sections yet (not yet converted)
    AND its source PDF is still in Drive. A statement whose PDF is missing is never wiped --
    it could never be re-created."""
    rows = db.execute(
        text(
            "SELECT bs.id::text AS id, bs.drive_file_id, bs.bank_name, "
            "EXISTS (SELECT 1 FROM statement_accounts sa WHERE sa.bank_statement_id = bs.id) AS converted "
            "FROM bank_statements bs ORDER BY bs.processed_at, bs.id"
        )
    ).all()
    result = WipeSet()
    for row in rows:
        if row.converted:
            result.already_converted += 1
        elif row.drive_file_id in drive_file_ids:
            result.statement_ids.append(row.id)
        else:
            result.kept_missing_pdf.append({"id": row.id, "drive_file_id": row.drive_file_id, "bank_name": row.bank_name})
    return result


def _count(db: Session, sql: str, ids: list[str]) -> int:
    return db.execute(text(sql), {"ids": ids}).scalar_one()


def scoped_counts(db: Session, ids: list[str]) -> dict[str, int]:
    return {
        "statements": len(ids),
        "transactions": _count(db, f"SELECT count(*) FROM transactions WHERE bank_statement_id = ANY({_IDS})", ids),
        "manual_corrections": _count(
            db,
            f"SELECT count(*) FROM transactions WHERE bank_statement_id = ANY({_IDS}) AND category_source = 'manual'",
            ids,
        ),
        "recategorization_jobs": _count(
            db, f"SELECT count(*) FROM recategorization_jobs WHERE source_transaction_id IN {_TXN_IDS}", ids
        ),
        "recategorization_proposals": _count(
            db,
            f"SELECT count(*) FROM recategorization_proposals WHERE candidate_transaction_id IN {_TXN_IDS} "
            f"OR recategorization_job_id IN {_JOB_IDS}",
            ids,
        ),
        "categorization_disagreements": _count(
            db, f"SELECT count(*) FROM categorization_disagreements WHERE transaction_id IN {_TXN_IDS}", ids
        ),
        "recurring_payment_matches": _count(
            db, f"SELECT count(*) FROM recurring_payment_matches WHERE transaction_id IN {_TXN_IDS}", ids
        ),
    }


def pre_flight(db: Session) -> list[str]:
    """WR-53: reasons to refuse (empty list = clear to go). Changes nothing."""
    reasons = []
    active_runs = db.execute(
        text("SELECT count(*) FROM ingestion_runs WHERE status IN ('queued', 'running')")
    ).scalar_one()
    if active_runs:
        reasons.append(f"{active_runs} ingestion run(s) are queued or running; wait for them to finish")
    active_jobs = db.execute(
        text("SELECT count(*) FROM recategorization_jobs WHERE status IN ('queued', 'running')")
    ).scalar_one()
    if active_jobs:
        reasons.append(f"{active_jobs} recategorization job(s) are queued or running; wait for them to finish")
    active_removals = db.execute(
        text("SELECT count(*) FROM statement_removal_jobs WHERE status IN ('queued', 'running', 'embeddings_pending')")
    ).scalar_one()
    if active_removals:  # Epic 14 (WR-69): a removal and the wipe must never interleave
        reasons.append(f"{active_removals} duplicate-statement removal(s) are queued or in progress; wait for them to finish")
    if db.query(User).first() is None:
        reasons.append("there is no user account to attribute the reingest run to")
    try:
        vector_store._client().get_collections()
    except Exception as exc:  # noqa: BLE001 - any failure means the vector store is not usable
        reasons.append(f"the vector store is unreachable ({exc})")
    return reasons


def list_drive_pdfs(db: Session) -> list:
    return drive_client.list_folder_pdf_files(db)


def dry_run(db: Session, drive_files: list) -> DryRun:
    wipe_set = compute_wipe_set(db, {f.id for f in drive_files})
    return DryRun(
        wipe_set=wipe_set,
        counts=scoped_counts(db, wipe_set.statement_ids),
        drive_pdf_count=len(drive_files),
        skip_plan=backfill_duplicates.plan_skips(db, wipe_set.statement_ids),
    )


def render_dry_run(report: DryRun) -> str:
    c = report.counts
    lines = [
        "DRY RUN -- nothing has been changed.",
        f"  Statements that would be wiped and re-ingested: {c['statements']}",
        f"  Transactions in them: {c['transactions']} (of which {c['manual_corrections']} manual category corrections, preserved)",
        "  Rows that depend on those transactions and would be DISCARDED:",
        f"    recategorization jobs: {c['recategorization_jobs']}",
        f"    recategorization proposals: {c['recategorization_proposals']}",
        f"    categorization disagreements: {c['categorization_disagreements']}",
        f"    recurring-payment matches: {c['recurring_payment_matches']} (re-derived by ingestion where they still apply)",
        f"  Statements already converted (left alone): {report.wipe_set.already_converted}",
        f"  Statements KEPT because their PDF is missing from Drive: {len(report.wipe_set.kept_missing_pdf)}",
        f"  PDFs currently in the Drive folder: {report.drive_pdf_count}",
    ]
    for kept in report.wipe_set.kept_missing_pdf:
        lines.append(f"    kept: {kept['bank_name'] or '(no bank name)'} (Drive file {kept['drive_file_id']})")
    lines += backfill_duplicates.render_plan(report.skip_plan)
    return "\n".join(lines)


def perform_wipe(db: Session, ids: list[str]) -> dict[str, int]:
    """WR-55: the whole wipe in the CALLER's single transaction, in BR-36 order, after
    detaching ingestion_run_files. Returns rows deleted per table. Scoped to `ids`, so a
    statement kept because its PDF is missing (and everything depending on it) is untouched.
    The SQL itself is the shared helper in duplicates/cascade.py (WR-68)."""
    return delete_statements(db, ids).counts


def reset_remaining_embeddings(db: Session) -> int:
    """After the vector collection is recreated empty (WR-52), every transaction that still
    exists has lost its vector, so it is reset to `pending` and the existing embedding
    mechanism re-embeds it. Categories are untouched (same as WR-39)."""
    return db.execute(text("UPDATE transactions SET embedding_status = 'pending' WHERE embedding_status <> 'pending'")).rowcount


def recreate_vector_collection(*, attempts: int = 3, sleep: Callable[[float], None] = time.sleep) -> None:
    for attempt in range(1, attempts + 1):
        if vector_store.recreate_transactions_collection():
            return
        logger.warning("Vector collection recreation failed (attempt %d/%d)", attempt, attempts)
        if attempt < attempts:
            sleep(2.0 * attempt)
    raise BackfillRefused(
        "the vector store collection could not be recreated; the reingest was NOT started. "
        "The database wipe has already committed -- fix the vector store and run `run` again."
    )


def start_reingest_run(db: Session) -> IngestionRun:
    """An ordinary ingestion run created already `running`, so it holds the single active-run
    slot (BR-10) and no normal run can be queued or started while it works."""
    user = db.query(User).first()
    run = IngestionRun(triggered_by_user_id=user.id, status=IngestionRunStatus.RUNNING)
    db.add(run)
    db.commit()
    return run


@dataclass
class RunOutcome:
    nothing_to_wipe: bool
    backup_folder: str | None
    deleted: dict[str, int]
    reingest_run_id: str | None


def run_backfill(
    db: Session,
    *,
    snapshot: Callable[[], AbstractContextManager[Connection]],
    confirm: Callable[[str], str],
    out: Callable[[str], None] = print,
    sleep: Callable[[float], None] = time.sleep,
) -> RunOutcome:
    """The `run` command. `snapshot` yields the connection the backup is read from (the CLI
    gives a REPEATABLE READ connection); `confirm` is the typed-confirmation prompt."""
    reasons = pre_flight(db)
    if reasons:
        raise BackfillRefused("refusing to start:\n  - " + "\n  - ".join(reasons))
    drive_files = list_drive_pdfs(db)
    report = dry_run(db, drive_files)
    out(render_dry_run(report))

    if not report.wipe_set.statement_ids:
        out("Nothing to wipe (every statement is already converted, or its PDF is missing from Drive). "
            "Going straight to the reingest; no new backup is taken.")
        run = start_reingest_run(db)
        pipeline.process_run(db, run, backfill_mode=True)
        return RunOutcome(True, None, {}, str(run.id))

    ids = report.wipe_set.statement_ids
    folder_name = export.backup_folder_name()
    with snapshot() as conn:
        artifact = export.build_backup(
            conn,
            extra_manifest={
                "wipe_set_statement_ids": ids,
                "kept_missing_pdf": report.wipe_set.kept_missing_pdf,
                "dry_run": report.counts,
                "backed_up_tables": list(BACKED_UP_TABLES),
            },
        )
    location = export.upload_backup(db, artifact, folder_name)
    problems = export.verify_uploaded_backup(db, location, artifact)
    if problems:
        raise BackfillRefused("the backup could not be verified, so NOTHING was wiped:\n  - " + "\n  - ".join(problems))
    out(f"Backup verified by download and checksum: Drive backup folder '{location.folder_name}'.")

    phrase = f"WIPE {len(ids)} STATEMENTS"
    typed = confirm(f"To proceed, type exactly: {phrase}\n> ")
    if typed.strip() != phrase:
        raise BackfillRefused("confirmation did not match; NOTHING was wiped.")

    # Epic 14 (WR-69): record each planned skip BEFORE the wipe, in the same transaction, so a wipe
    # that rolls back leaves nothing registered. The remembered files hold content hashes, not
    # statement ids (BR-50), so the wipe does not touch them.
    registered = backfill_duplicates.pre_register(db, report.skip_plan)
    deleted = perform_wipe(db, ids)
    expected = report.counts
    if deleted["bank_statements"] != expected["statements"] or deleted["transactions"] != expected["transactions"]:
        db.rollback()
        raise BackfillRefused(
            f"the wipe deleted {deleted['bank_statements']} statements / {deleted['transactions']} transactions "
            f"but the dry run said {expected['statements']} / {expected['transactions']}; it was rolled back."
        )
    db.commit()
    out(f"Wiped {deleted['bank_statements']} statements and {deleted['transactions']} transactions; "
        f"{registered} probable-duplicate copy(ies) registered to be skipped.")

    recreate_vector_collection(sleep=sleep)
    requeued = reset_remaining_embeddings(db)
    db.commit()
    out(f"Vector collection recreated; {requeued} remaining transaction(s) queued for re-embedding.")

    out("Starting the reingest. This re-reads every PDF and takes as long as the original ingestion.")
    run = start_reingest_run(db)
    pipeline.process_run(db, run, backfill_mode=True)
    db.refresh(run)
    out(f"Reingest run finished with status '{run.status.value}'. Next: finish --backup {folder_name}")
    return RunOutcome(False, folder_name, deleted, str(run.id))
