"""The completion report (WR-56): printed, and saved as text and JSON beside the backup."""

import json
from dataclasses import asdict

from sqlalchemy import text
from sqlalchemy.orm import Session

from ingestion_worker.backfill.corrections import CorrectionResult
from ingestion_worker.backfill.export import BackupArtifact, BackupLocation, read_rows
from ingestion_worker.clients import drive_client
from ingestion_worker.duplicates import service as duplicates_service


def build_report(
    db: Session, artifact: BackupArtifact, corrections: CorrectionResult, drive_files: list
) -> dict:
    manifest = artifact.manifest
    # "What this backfill produced" is identified by id, not by timestamp: the backup lists
    # every statement and run-file that existed before the wipe, so anything not in it is new.
    # (Comparing the tool's clock with the database's would be fragile for no benefit.)
    old_statement_ids = [r["id"] for r in read_rows(artifact, "bank_statements")]
    old_run_file_ids = [r["id"] for r in read_rows(artifact, "ingestion_run_files")]
    params = {"old_statements": old_statement_ids, "old_run_files": old_run_file_ids}
    new_statements = db.execute(
        text(
            "SELECT bs.id::text AS id, bs.bank_name, "
            "(SELECT f.drive_file_name FROM ingestion_run_files f WHERE f.drive_file_id = bs.drive_file_id "
            " ORDER BY f.processed_at DESC LIMIT 1) AS file_name, "
            "(SELECT count(*) FROM statement_accounts sa WHERE sa.bank_statement_id = bs.id) AS sections "
            "FROM bank_statements bs WHERE bs.id <> ALL(CAST(:old_statements AS uuid[])) ORDER BY bs.processed_at, bs.id"
        ),
        params,
    ).all()
    per_statement = [{"statement_id": r.id, "file": r.file_name, "bank": r.bank_name, "sections": r.sections} for r in new_statements]
    failed = db.execute(
        text(
            "SELECT DISTINCT ON (f.drive_file_id) f.drive_file_name AS file_name, f.failure_reason AS reason "
            "FROM ingestion_run_files f WHERE f.outcome = 'failed' AND f.id <> ALL(CAST(:old_run_files AS uuid[])) "
            "AND f.drive_file_id NOT IN (SELECT drive_file_id FROM bank_statements) "
            "ORDER BY f.drive_file_id, f.processed_at DESC"
        ),
        params,
    ).all()
    # A Drive file with no statement of its own is either (a) a byte-identical copy of another
    # file, correctly skipped as a duplicate by this reingest, or (b) genuinely not ingested yet.
    # Telling the user (b) for an (a) file would send them round in circles re-running ingestion.
    skipped_copies = {
        r.drive_file_id: r.drive_file_name
        for r in db.execute(
            text(
                "SELECT DISTINCT ON (drive_file_id) drive_file_id, drive_file_name FROM ingestion_run_files "
                "WHERE outcome = 'skipped_duplicate' AND id <> ALL(CAST(:old_run_files AS uuid[])) "
                "ORDER BY drive_file_id, processed_at DESC"
            ),
            params,
        ).all()
    }
    # Epic 14 (WR-69): files the reingest skipped as PROBABLE duplicates (pre-registered or flagged
    # inline). Like an exact copy, such a file has no statement of its own and must not be reported as
    # "not ingested yet" (that would send the user round in circles re-running ingestion).
    probable_rows = db.execute(
        text(
            "SELECT DISTINCT ON (f.drive_file_id) f.drive_file_id, f.drive_file_name, f.duplicate_comparison_id::text AS comparison_id, "
            "c.earlier_file_name, c.later_file_name, c.earlier_content_hash, c.reason, k.matched_statement_hash "
            "FROM ingestion_run_files f JOIN duplicate_comparisons c ON c.id = f.duplicate_comparison_id "
            "LEFT JOIN known_files k ON k.comparison_id = c.id "
            "WHERE f.outcome = 'skipped_probable_duplicate' AND f.id <> ALL(CAST(:old_run_files AS uuid[])) "
            "ORDER BY f.drive_file_id, f.processed_at DESC"
        ),
        params,
    ).all()
    probable_skips = [
        {
            "file": r.drive_file_name,
            "duplicate_of": (r.earlier_file_name if r.matched_statement_hash == r.earlier_content_hash else r.later_file_name),
            "reason": r.reason,
            "comparison_id": r.comparison_id,
        }
        for r in probable_rows
    ]
    probable_ids = {r.drive_file_id for r in probable_rows}
    not_ingested = []
    identical_copies = []
    for f in drive_files:
        if db.execute(text("SELECT 1 FROM bank_statements WHERE drive_file_id = :d"), {"d": f.id}).first():
            continue
        if f.id in probable_ids:
            continue
        (identical_copies if f.id in skipped_copies else not_ingested).append(f.name)
    findings, _near = duplicates_service.compute_findings(db, duplicates_service.current_settings())
    different_size_left = [
        {
            "files": [f.earlier.file_name or f.earlier.content_hash[:8], f.later.file_name or f.later.content_hash[:8]],
            "reason": f.draft.reason,
        }
        for f in findings
        if not f.removal_allowed and f.existing_status in (None, duplicates_service.DuplicatePairStatus.PENDING)
    ]
    rederived = db.execute(
        text(
            "SELECT count(*) FROM recurring_payment_matches m JOIN transactions t ON t.id = m.transaction_id "
            "JOIN bank_statements bs ON bs.id = t.bank_statement_id WHERE bs.id <> ALL(CAST(:old_statements AS uuid[]))"
        ),
        params,
    ).scalar_one()
    recategorized_fresh = db.execute(
        text(
            "SELECT count(*) FROM transactions t JOIN bank_statements bs ON bs.id = t.bank_statement_id "
            "WHERE bs.id <> ALL(CAST(:old_statements AS uuid[])) AND t.category_source <> 'manual'"
        ),
        params,
    ).scalar_one()
    dry = manifest.get("dry_run", {})
    return {
        "backup_taken_at": manifest["created_at"],
        "statements_wiped": dry.get("statements"),
        "statements_reingested": len(per_statement),
        "statements_kept_missing_pdf": manifest.get("kept_missing_pdf", []),
        "pdfs_failed_to_reingest": [{"file": f.file_name, "reason": f.reason} for f in failed],
        "drive_pdfs_without_a_statement": not_ingested,
        "identical_copies_skipped_as_duplicates": identical_copies,
        "manual_corrections": {
            "captured": corrections.captured,
            "applied": corrections.applied,
            "already_applied": corrections.already_applied,
            "unmatched": [asdict(c) | {"amount": str(c.amount)} for c in corrections.unmatched],
            "placed_by_date_and_amount": [
                asdict(p.correction) | {"amount": str(p.correction.amount), "new_description": p.new_description}
                for p in corrections.loosely_placed
            ],
            "carried_from_skipped_copies": corrections.carried,
            "carried_and_placed": corrections.carried_applied,
            "superseded_by_the_kept_copys_own": [asdict(c) | {"amount": str(c.amount)} for c in corrections.superseded],
        },
        "probable_duplicates_skipped": probable_skips,
        "different_size_pairs_left_for_the_review_panel": different_size_left,
        "non_manual_transactions_recategorized_fresh": recategorized_fresh,
        "recurring_payment_matches_discarded": dry.get("recurring_payment_matches"),
        "recurring_payment_matches_rederived": rederived,
        "discarded_dependent_rows": {
            k: dry.get(k) for k in ("recategorization_jobs", "recategorization_proposals", "categorization_disagreements", "recurring_payment_matches")
        },
        "statements": per_statement,
        "multi_account_statements": [s for s in per_statement if s["sections"] > 1],
    }


def render_report(report: dict) -> str:
    c = report["manual_corrections"]
    lines = [
        "BACKFILL COMPLETION REPORT",
        f"  Backup taken at: {report['backup_taken_at']}",
        f"  Statements wiped: {report['statements_wiped']}; re-ingested: {report['statements_reingested']}",
        f"  Manual corrections: {c['captured']} captured, {c['applied']} re-applied, {c['already_applied']} already in place, {len(c['unmatched'])} UNMATCHED",
        f"  Other transactions recategorized fresh by the pipeline (may differ from before): {report['non_manual_transactions_recategorized_fresh']}",
        f"  Recurring-payment matches: {report['recurring_payment_matches_discarded']} discarded, {report['recurring_payment_matches_rederived']} re-derived",
        f"  Other dependent rows discarded: {report['discarded_dependent_rows']}",
    ]
    if report["statements_kept_missing_pdf"]:
        lines.append(f"  Statements KEPT because their PDF is missing from Drive ({len(report['statements_kept_missing_pdf'])}):")
        lines += [f"    - {k['bank_name']} (Drive file {k['drive_file_id']})" for k in report["statements_kept_missing_pdf"]]
    if report["pdfs_failed_to_reingest"]:
        lines.append(f"  PDFs that FAILED to reingest ({len(report['pdfs_failed_to_reingest'])}):")
        lines += [f"    - {f['file']}: {f['reason']}" for f in report["pdfs_failed_to_reingest"]]
    if report["identical_copies_skipped_as_duplicates"]:
        lines.append(
            f"  Byte-identical copies skipped as duplicates ({len(report['identical_copies_skipped_as_duplicates'])}): "
            + ", ".join(report["identical_copies_skipped_as_duplicates"])
        )
    if report["drive_pdfs_without_a_statement"]:
        lines.append(f"  Drive PDFs with no statement yet ({len(report['drive_pdfs_without_a_statement'])}): run ingestion again, then re-run `finish`.")
    skipped = report["probable_duplicates_skipped"]
    lines.append(f"  Probable duplicates skipped by the reingest: {len(skipped)}")
    lines += [f"    - {s['file']}: probable duplicate of {s['duplicate_of']} (comparison {s['comparison_id']}). {s['reason']}" for s in skipped]
    if skipped:
        lines.append("    (open a skipped file's comparison in the app to override it if it was not a duplicate)")
    if c["carried_from_skipped_copies"]:
        lines.append(
            f"  Manual corrections carried from a skipped copy to the kept copy: {c['carried_and_placed']} of "
            f"{c['carried_from_skipped_copies']} placed; {len(c['superseded_by_the_kept_copys_own'])} superseded by a correction the kept copy already had"
        )
        lines += [
            f"    - superseded: {u['transaction_date']} {u['amount']} {u['direction']} {u['description']!r} (category {u['category_id']})"
            for u in c["superseded_by_the_kept_copys_own"]
        ]
    different = report["different_size_pairs_left_for_the_review_panel"]
    if different:
        lines.append(f"  Pairs of clearly different sizes, left for the Review panel as information only ({len(different)}):")
        lines += [f"    - {' / '.join(d['files'])}: {d['reason']}" for d in different]
    if c.get("placed_by_date_and_amount"):
        lines.append(
            f"  Manual corrections placed by date and amount because the re-read description differs slightly "
            f"({len(c['placed_by_date_and_amount'])}; check by eye):"
        )
        lines += [
            f"    - {u['transaction_date']} {u['amount']} {u['direction']} {u['description']!r} -> {u['new_description']!r} (category {u['category_id']})"
            for u in c["placed_by_date_and_amount"]
        ]
    if c["unmatched"]:
        lines.append("  UNMATCHED manual corrections (not re-applied):")
        lines += [f"    - {u['transaction_date']} {u['amount']} {u['direction']} {u['description']!r} (category {u['category_id']})" for u in c["unmatched"]]
    multi = report["multi_account_statements"]
    lines.append(f"  Statements with more than one account section: {len(multi)}")
    lines += [f"    - {m['file'] or m['statement_id']} ({m['bank']}): {m['sections']} accounts" for m in multi]
    lines.append("  Account sections per statement:")
    lines += [f"    {s['file'] or s['statement_id']} ({s['bank']}): {s['sections']}" for s in report["statements"]]
    return "\n".join(lines)


def save_report(db: Session, location: BackupLocation, report: dict, rendered: str) -> None:
    drive_client.upload_file(db, location.folder_id, "completion-report.json", json.dumps(report, indent=2, default=str).encode(), "application/json")
    drive_client.upload_file(db, location.folder_id, "completion-report.txt", rendered.encode(), "text/plain")
