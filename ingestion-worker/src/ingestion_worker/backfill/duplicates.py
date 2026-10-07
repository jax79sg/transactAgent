"""The Backfill Tool's probable-duplicate handling (WR-69, FR-PD-15..17).

`check-duplicates` is the read-only accuracy evaluation (NFR-PD-1). `plan_skips` decides which copy
the reingest will skip, `pre_register` records that decision as remembered files so the reingest's
ordinary pre-extraction lookup skips them whichever file Drive lists first, and the helpers at the
bottom carry manual corrections from a skipped copy to the kept one.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session
from transactagent_db.models import BankStatement, DuplicatePairStatus, KnownFileState

from ingestion_worker.duplicates import repository, service
from ingestion_worker.duplicates.service import NearMiss, PairFinding

_CHAIN_LIMIT = 10  # a copy skipped in favour of a copy that was itself skipped: follow, but never loop


@dataclass
class PlannedSkip:
    skip_hash: str
    kept_hash: str
    finding: PairFinding


@dataclass
class SkipPlan:
    skips: list[PlannedSkip] = field(default_factory=list)
    different_size: list[PairFinding] = field(default_factory=list)  # flagged, NOT skipped (Question 1 = C)
    left_for_panel: list[tuple[PairFinding, str]] = field(default_factory=list)
    dismissed: int = 0


def plan_skips(db: Session, wipe_statement_ids: list[str]) -> SkipPlan:
    """Which copy of each pair the reingest will skip. Nothing is written."""
    findings, _near = service.compute_findings(db, service.current_settings())
    wipe_hashes = (
        set(db.scalars(select(BankStatement.pdf_content_hash).where(BankStatement.id.in_(wipe_statement_ids))))
        if wipe_statement_ids
        else set()
    )
    plan = SkipPlan()
    planned: set[str] = set()
    for finding in sorted(findings, key=lambda f: (f.keep_hash, f.remove_hash)):
        if finding.existing_status == DuplicatePairStatus.DISMISSED:
            plan.dismissed += 1  # the user said it is not a duplicate: neither skipped nor listed
            continue
        if finding.existing_status in (DuplicatePairStatus.REMOVED, DuplicatePairStatus.SUPERSEDED):
            continue
        if not finding.removal_allowed:
            plan.different_size.append(finding)
            continue
        if finding.remove_hash not in wipe_hashes:
            plan.left_for_panel.append(
                (finding, "the copy to skip is not re-read (its PDF is missing from Drive, or it is already converted)")
            )
            continue
        if finding.remove_hash in planned:
            continue  # three copies: it is already being skipped in favour of another copy
        planned.add(finding.remove_hash)
        plan.skips.append(PlannedSkip(finding.remove_hash, finding.keep_hash, finding))
    return plan


def pre_register(db: Session, plan: SkipPlan) -> int:
    """Record each planned skip as a `probable_duplicate` remembered file (pointing at the kept
    copy and reusing the pair's comparison) and mark its pending pair superseded. The caller runs
    this in the SAME transaction as the wipe, so a rolled-back wipe leaves nothing registered. The
    remembered files hold content hashes, not statement ids (BR-50), so the wipe does not touch them."""
    pairs = repository.load_pairs(db)
    for skip in plan.skips:
        finding = skip.finding
        pair = pairs.get(finding.key)
        comparison_id = pair.comparison_id if pair is not None else repository.create_comparison(db, finding.draft).id
        repository.insert_known_file(
            db,
            content_hash=skip.skip_hash,
            state=KnownFileState.PROBABLE_DUPLICATE,
            matched_hash=skip.kept_hash,
            comparison_id=comparison_id,
        )
        if pair is not None and pair.status == DuplicatePairStatus.PENDING:
            repository.supersede_pair(db, pair)
    db.flush()
    return len(plan.skips)


def _describe(finding: PairFinding) -> list[str]:
    e, la = finding.earlier, finding.later
    def label(side):
        return f"{side.file_name or '(unknown file)'} [{side.content_hash[:8]}]"
    keep, remove = (e, la) if finding.keep_hash == e.content_hash else (la, e)
    v = finding.verdict
    return [
        f"  {e.bank_name}: {label(e)} ({len(e.transactions)} txns) and {label(la)} ({len(la.transactions)} txns)",
        f"      {v.matched_count} of {v.smaller_count} match (ratio {v.ratio}); would keep {label(keep)}, remove {label(remove)}",
        f"      manual corrections: kept copy {finding.corrections[keep.content_hash]}, other copy {finding.corrections[remove.content_hash]}; "
        + ("removal offered" if finding.removal_allowed else "sizes differ clearly: information only, no removal offered")
        + (f"; already {finding.existing_status.value}" if finding.existing_status else ""),
        f"      {finding.draft.reason}",
    ]


def render_check(findings: list[PairFinding], near: list[NearMiss], settings) -> str:
    lines = [
        "PROBABLE DUPLICATE CHECK -- read-only; nothing has been changed, no Drive or Gemini call was made.",
        f"  Rule: at least {settings.match_ratio} of the smaller statement's transactions match; "
        f"statements under {settings.min_transactions} transactions need a matching account identifier and closing balance too.",
        f"  Pairs flagged: {len(findings)} ({sum(1 for f in findings if f.removal_allowed)} with removal offered)",
    ]
    for finding in findings:
        lines += _describe(finding)
    lines.append(f"  Near misses (same bank, overlapping period, at least one shared transaction, NOT flagged): {len(near)}")
    for miss in near:
        lines.append(
            f"  {miss.earlier.bank_name}: {miss.earlier.file_name or '(unknown file)'} [{miss.earlier.content_hash[:8]}] "
            f"({len(miss.earlier.transactions)} txns) and {miss.later.file_name or '(unknown file)'} "
            f"[{miss.later.content_hash[:8]}] ({len(miss.later.transactions)} txns)"
        )
        lines.append(f"      not flagged because: {miss.why_not}")
    return "\n".join(lines)


def check_duplicates(db: Session, out=print) -> tuple[list[PairFinding], list[NearMiss]]:
    """`check-duplicates`: the rule applied to every held statement with the current settings,
    whatever the detection switch says. Read-only."""
    settings = service.current_settings()
    findings, near = service.compute_findings(db, settings)
    out(render_check(findings, near, settings))
    return findings, near


def render_plan(plan: SkipPlan) -> list[str]:
    """The dry run's duplicate section (FR-PD-15)."""
    lines = [f"  Probable duplicate pairs: {len(plan.skips)} copy(ies) will be SKIPPED by the reingest:"]
    for skip in plan.skips:
        f = skip.finding
        side = f.earlier if f.earlier.content_hash == skip.skip_hash else f.later
        kept = f.earlier if side is f.later else f.later
        lines.append(
            f"    - skip {side.file_name or '(unknown file)'} [{side.content_hash[:8]}], keep "
            f"{kept.file_name or '(unknown file)'} [{kept.content_hash[:8]}] ({f.verdict.matched_count} of {f.verdict.smaller_count} match)"
        )
    if plan.different_size:
        lines.append(f"  Pairs of clearly different sizes, NOT skipped (both are re-ingested; listed in the Review panel): {len(plan.different_size)}")
    if plan.left_for_panel:
        lines.append(f"  Pairs left for the Review panel ({len(plan.left_for_panel)}):")
        lines += [f"    - {f.earlier.file_name or f.earlier.content_hash[:8]} / {f.later.file_name or f.later.content_hash[:8]}: {why}" for f, why in plan.left_for_panel]
    if plan.dismissed:
        lines.append(f"  Pairs you dismissed as not duplicates (honoured, not skipped): {plan.dismissed}")
    return lines


# ---- carrying manual corrections from a skipped copy to the kept copy (FR-PD-17) -----------------


def kept_target(db: Session, content_hash: str) -> str | None:
    """The hash of the statement that now stands for `content_hash`: itself if a statement with it
    exists, otherwise the statement its remembered file points at, following a chain of skipped
    copies. None when there is no such statement."""
    seen: set[str] = set()
    current = content_hash
    for _ in range(_CHAIN_LIMIT):
        if current in seen:
            return None
        seen.add(current)
        if db.scalar(select(BankStatement.id).where(BankStatement.pdf_content_hash == current)) is not None:
            return current
        known = repository.get_known_file(db, current)
        if known is None:
            return None
        current = known.matched_statement_hash
    return None


def request_pair_scan(db: Session) -> None:
    """WR-69: `finish` asks the worker for a pair scan, because the re-created statements may now carry
    account identifiers and closing balances, which can make small statements flaggable. Only a request:
    the worker acts on it at its next due check."""
    repository.get_or_create_scan_state(db).recheck_requested_at = datetime.now(UTC)
    db.flush()

