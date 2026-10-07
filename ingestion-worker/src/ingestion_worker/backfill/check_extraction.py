"""`check-extraction` (read-only): compare the NEW extraction with what the database already
holds, on real PDFs, before any wipe is proposed (NFR-AB-3). Also reveals which PDFs are
multi-account. Writes NOTHING to the database or to Drive: the session is put in a
READ ONLY transaction, so an accidental write would raise.

It does call Gemini once per PDF, exactly as normal ingestion does, so it costs API quota in
proportion to the number of PDFs checked.
"""

import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

from ingestion_worker.clients import drive_client
from ingestion_worker.extraction.service import ExtractionFailure, extract_statement

logger = logging.getLogger(__name__)


@dataclass
class Comparison:
    bank: str | None
    drive_file_id: str
    status: str  # "ok" | "mismatch" | "extraction_failed" | "pdf_missing_from_drive"
    sections: int = 0
    stored_count: int = 0
    new_count: int = 0
    only_stored: int = 0
    only_new: int = 0
    account_tails: list[str] = field(default_factory=list)
    detail: str = ""


def _stored_transactions(db: Session, statement_id) -> Counter:
    rows = db.execute(
        text(
            "SELECT transaction_date::text AS d, COALESCE(out_flow, in_flow) AS amount, "
            "CASE WHEN out_flow IS NOT NULL THEN 'out' ELSE 'in' END AS direction, description "
            "FROM transactions WHERE bank_statement_id = :s"
        ),
        {"s": statement_id},
    ).all()
    return Counter((r.d, r.amount, r.direction, r.description) for r in rows)


def choose_statements(db: Session, *, limit: int | None) -> list:
    """Round-robin across banks (oldest first within each), so a small sample still spans
    every bank; `limit=None` means all."""
    rows = db.execute(
        text("SELECT id, drive_file_id, bank_name FROM bank_statements ORDER BY bank_name NULLS LAST, processed_at, id")
    ).all()
    by_bank: dict = {}
    for row in rows:
        by_bank.setdefault(row.bank_name, []).append(row)
    ordered = []
    while any(by_bank.values()):
        for bank in list(by_bank):
            if by_bank[bank]:
                ordered.append(by_bank[bank].pop(0))
    return ordered if limit is None else ordered[:limit]


def check_extraction(
    db: Session, *, limit: int | None, drive_files: list, out: Callable[[str], None] = print
) -> list[Comparison]:
    db.execute(text("SET TRANSACTION READ ONLY"))
    drive_by_id = {f.id: f for f in drive_files}
    results = []
    for statement in choose_statements(db, limit=limit):
        ref = drive_by_id.get(statement.drive_file_id)
        if ref is None:
            results.append(Comparison(statement.bank_name, statement.drive_file_id, "pdf_missing_from_drive"))
            continue
        extracted = extract_statement(drive_client.download_file(db, ref))
        if isinstance(extracted, ExtractionFailure):
            results.append(Comparison(statement.bank_name, statement.drive_file_id, "extraction_failed", detail=extracted.reason))
            continue
        stored = _stored_transactions(db, statement.id)
        new = Counter((str(t.transaction_date), t.amount, t.direction.value, t.description) for t in extracted.transactions)
        only_stored, only_new = sum((stored - new).values()), sum((new - stored).values())
        results.append(
            Comparison(
                bank=statement.bank_name, drive_file_id=statement.drive_file_id,
                status="ok" if not only_stored and not only_new else "mismatch",
                sections=len(extracted.sections), stored_count=sum(stored.values()), new_count=sum(new.values()),
                only_stored=only_stored, only_new=only_new,
                account_tails=[(s.account_identifier or "")[-4:] or "(none)" for s in extracted.sections],
            )
        )
        out(render_one(results[-1]))
    return results  # the read-only transaction ends when the caller's session scope closes; nothing was written


def render_one(c: Comparison) -> str:
    base = f"{c.bank or '(no bank)'} [{c.drive_file_id}] {c.status.upper()}"
    if c.status in ("ok", "mismatch"):
        base += (f": {c.sections} account section(s) {c.account_tails}; transactions stored {c.stored_count} vs new {c.new_count}"
                 f" (only stored: {c.only_stored}, only new: {c.only_new})" + ("  <-- MULTI-ACCOUNT" if c.sections > 1 else ""))
    elif c.detail:
        base += f": {c.detail}"
    return base


def render_summary(results: list[Comparison]) -> str:
    counts = Counter(r.status for r in results)
    multi = [r for r in results if r.sections > 1]
    lines = [f"Checked {len(results)} statement(s): " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))]
    lines.append(f"Multi-account PDFs among them: {len(multi)}")
    lines += [f"  - {m.bank} [{m.drive_file_id}]: {m.sections} sections {m.account_tails}" for m in multi]
    return "\n".join(lines)
