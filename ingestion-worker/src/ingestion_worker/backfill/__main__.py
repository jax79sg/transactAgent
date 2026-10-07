"""Command-line entry point for the Epic 13 backfill:

    python -m ingestion_worker.backfill check-extraction [--limit N | --all]
    python -m ingestion_worker.backfill check-duplicates
    python -m ingestion_worker.backfill run
    python -m ingestion_worker.backfill finish  --backup <folder>
    python -m ingestion_worker.backfill restore --backup <folder>

Run through `docker compose` with the `ingestion-worker` SERVICE STOPPED (see the runbook in
aidlc-docs/construction/ingestion-worker/code/account-balance-summary.md). Never triggered
by the poll loop, a deploy, a migration, or a normal ingestion run.
"""

import argparse
import logging
import sys
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

from transactagent_db.migrate import run_migrations_with_lock

from ingestion_worker.backfill import check_extraction as check_mod
from ingestion_worker.backfill import corrections, export, report, restore, service
from ingestion_worker.backfill import duplicates as duplicates_mod
from ingestion_worker.db import engine, session_scope
from ingestion_worker.logging_capture import DbLogHandler

logger = logging.getLogger(__name__)

_DATABASE_ALEMBIC_INI = Path(__file__).resolve().parents[4] / "database" / "alembic.ini"


@contextmanager
def _repeatable_read_snapshot():
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        yield conn


def _interactive_confirm(prompt: str) -> str:
    if not sys.stdin.isatty():
        raise service.BackfillRefused("a typed confirmation is required, but this is not an interactive terminal")
    return input(prompt)


def cmd_check_extraction(args, out: Callable[[str], None] = print) -> int:
    with session_scope() as db:
        files = service.list_drive_pdfs(db)
        results = check_mod.check_extraction(db, limit=None if args.all else args.limit, drive_files=files, out=out)
    out(check_mod.render_summary(results))
    return 0


def cmd_check_duplicates(args, out: Callable[[str], None] = print) -> int:
    """Epic 14 (WR-69, NFR-PD-1): the accuracy evaluation. Read-only: no Drive, no Gemini, nothing written."""
    with session_scope() as db:
        duplicates_mod.check_duplicates(db, out)
    return 0


def cmd_run(args, out: Callable[[str], None] = print) -> int:
    logging.getLogger().addHandler(DbLogHandler())
    with session_scope() as db:
        service.run_backfill(db, snapshot=_repeatable_read_snapshot, confirm=_interactive_confirm, out=out)
    return 0


def cmd_finish(args, out: Callable[[str], None] = print) -> int:
    with session_scope() as db:
        location, artifact = export.load_backup(db, args.backup)
        captured = corrections.capture_corrections(artifact)
        # Epic 14 (FR-PD-17): corrections whose statement was skipped as a probable duplicate go to the kept copy.
        captured = corrections.rekey_for_skipped_copies(db, captured)
        result = corrections.apply_corrections(db, captured)
        files = service.list_drive_pdfs(db)
        data = report.build_report(db, artifact, result, files)
        rendered = report.render_report(data)
        report.save_report(db, location, data, rendered)
        # Epic 14 (WR-69): the re-created statements may now carry account identifiers and closing
        # balances, which can make small statements flaggable, so ask the worker for a pair scan.
        duplicates_mod.request_pair_scan(db)
    out(rendered)
    return 0


def cmd_restore(args, out: Callable[[str], None] = print) -> int:
    with session_scope() as db:
        _, artifact = export.load_backup(db, args.backup)
        restore.restore_backup(db, artifact, confirm=_interactive_confirm, folder_name=args.backup, out=out)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m ingestion_worker.backfill")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check-extraction", help="read-only: compare the new extraction with stored data on real PDFs")
    group = check.add_mutually_exclusive_group()
    group.add_argument("--limit", type=int, default=10, help="how many statements to check (default 10, spread across banks)")
    group.add_argument("--all", action="store_true", help="check every statement (one Gemini call each)")
    sub.add_parser("check-duplicates", help="read-only: list probable-duplicate pairs and near misses among the stored statements")
    sub.add_parser("run", help="dry run, verified backup, typed confirmation, wipe, reingest")
    for name, help_text in (("finish", "re-apply manual corrections and write the completion report"),
                            ("restore", "restore the backed-up tables")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--backup", required=True, help="the backup folder name printed by `run`")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    run_migrations_with_lock(_DATABASE_ALEMBIC_INI)  # idempotent; same startup pattern as the worker
    handlers = {
        "check-extraction": cmd_check_extraction,
        "check-duplicates": cmd_check_duplicates,
        "run": cmd_run,
        "finish": cmd_finish,
        "restore": cmd_restore,
    }
    try:
        return handlers[args.command](args)
    except (service.BackfillRefused, export.BackupError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
