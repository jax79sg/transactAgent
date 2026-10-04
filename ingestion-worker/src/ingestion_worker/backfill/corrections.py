"""Preserving manual category corrections across the backfill (WR-55).

Captured from the BACKUP ARTIFACT (never from memory, so a crash cannot lose them) and
re-applied after the reingest by matching on (statement content hash, transaction date,
amount, direction, description) as a MULTISET: identical rows are interchangeable from the
user's point of view, so for each key as many captured corrections are applied as there
are reingested rows, in a deterministic order, and any surplus is reported. Applied by
direct writes -- never through the normal manual-correction path, so no recategorization
jobs are created (that would trigger a re-scan storm).
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field, replace
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from ingestion_worker.backfill.duplicates import kept_target
from ingestion_worker.backfill.export import BackupArtifact, read_rows

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CapturedCorrection:
    statement_content_hash: str
    transaction_date: str
    amount: Decimal
    direction: str  # "out" | "in"
    description: str
    category_id: str
    # Epic 14 (FR-PD-17): re-keyed from a copy the reingest skipped as a probable duplicate onto the
    # copy that was kept. Not part of the matching key; it only decides who wins a conflict.
    carried: bool = False

    @property
    def key(self) -> tuple:
        return (self.statement_content_hash, self.transaction_date, self.amount, self.direction, self.description)


@dataclass
class CorrectionResult:
    captured: int = 0
    applied: int = 0
    already_applied: int = 0
    unmatched: list[CapturedCorrection] = field(default_factory=list)
    # Epic 14: corrections carried from a skipped copy to the kept copy, how many of them were
    # applied, and those left over because the kept copy had its own correction on that transaction
    # (the kept copy's own corrections win, WR-69).
    carried: int = 0
    carried_applied: int = 0
    superseded: list[CapturedCorrection] = field(default_factory=list)


def capture_corrections(artifact: BackupArtifact) -> list[CapturedCorrection]:
    """Every manual correction in the backup that belongs to a statement the backfill wiped.
    (A statement kept because its PDF is missing was never wiped, so its manual corrections
    were never at risk and are not touched.)"""
    wipe_set = set(artifact.manifest.get("wipe_set_statement_ids", []))
    hash_by_statement = {row["id"]: row["pdf_content_hash"] for row in read_rows(artifact, "bank_statements")}
    captured = []
    for row in read_rows(artifact, "transactions"):
        if row["category_source"] != "manual" or row["bank_statement_id"] not in wipe_set:
            continue
        outgoing = row["out_flow"] is not None
        captured.append(
            CapturedCorrection(
                statement_content_hash=hash_by_statement[row["bank_statement_id"]],
                transaction_date=row["transaction_date"],
                amount=Decimal(row["out_flow"] if outgoing else row["in_flow"]),
                direction="out" if outgoing else "in",
                description=row["description"],
                category_id=row["category_id"],
            )
        )
    return captured


def rekey_for_skipped_copies(db: Session, captured: list[CapturedCorrection]) -> list[CapturedCorrection]:
    """FR-PD-17: a correction whose statement was skipped as a probable duplicate (so no statement
    with that content hash exists any more) is re-keyed to the copy that was kept, found through the
    skipped file's remembered record (following a chain of skipped copies). Corrections whose
    statement does exist, or that lead nowhere, are left exactly as they were, so a genuinely
    unmatched correction is still reported as unmatched."""
    targets: dict[str, str | None] = {}
    rekeyed = []
    for correction in captured:
        original = correction.statement_content_hash
        if original not in targets:
            targets[original] = kept_target(db, original)
        target = targets[original]
        rekeyed.append(correction if target is None or target == original else replace(correction, statement_content_hash=target, carried=True))
    return rekeyed


def apply_corrections(db: Session, captured: list[CapturedCorrection]) -> CorrectionResult:
    result = CorrectionResult(captured=len(captured), carried=sum(1 for c in captured if c.carried))
    groups: dict[tuple, list[CapturedCorrection]] = defaultdict(list)
    for correction in captured:
        groups[correction.key].append(correction)

    for (content_hash, txn_date, amount, direction, description), corrections in groups.items():
        flow_column = "out_flow" if direction == "out" else "in_flow"
        rows = db.execute(
            text(
                f"SELECT t.id, t.category_id::text AS category_id, t.category_source::text AS category_source "
                f"FROM transactions t JOIN bank_statements bs ON bs.id = t.bank_statement_id "
                f"WHERE bs.pdf_content_hash = :h AND t.transaction_date = :d AND t.{flow_column} = :a "
                f"AND t.description = :desc ORDER BY t.created_at, t.id"
            ),
            {"h": content_hash, "d": txn_date, "a": amount, "desc": description},
        ).all()
        # Deterministic pairing: the kept copy's OWN corrections first (they win a conflict, WR-69), then
        # carried ones, each sorted by category so ties are stable.
        ordered = sorted(corrections, key=lambda c: (c.carried, c.category_id))
        for correction, row in zip(ordered, rows, strict=False):
            if correction.carried:
                result.carried_applied += 1
            if row.category_source == "manual" and row.category_id == correction.category_id:
                result.already_applied += 1
                continue
            db.execute(
                text(
                    "UPDATE transactions SET category_id = CAST(:c AS uuid), category_source = 'manual', "
                    "updated_at = now() WHERE id = :i"
                ),
                {"c": correction.category_id, "i": row.id},
            )
            result.applied += 1
        has_own = any(not c.carried for c in corrections)
        for leftover in ordered[len(rows):]:
            # A carried correction with no free row, in a group where the kept copy has its own
            # correction, was superseded by it; anything else left over is genuinely unmatched.
            (result.superseded if leftover.carried and has_own else result.unmatched).append(leftover)
    db.flush()
    return result
