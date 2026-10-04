"""The Probable Duplicate Detector's database-facing steps (WR-59 to WR-64).

The matching rule itself is in `matching.py` (pure). This module decides *which* statements to
compare, writes the evidence (comparison + remembered file), and runs the pair scan.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from itertools import combinations

from sqlalchemy.orm import Session
from transactagent_db.models import DuplicatePairStatus, KnownFileState

from ingestion_worker import config
from ingestion_worker.accounts.normalize import bank_key, normalize_identifier
from ingestion_worker.duplicates import matching, repository
from ingestion_worker.duplicates.matching import (
    AccountFact,
    CopyFacts,
    DetectionSettings,
    SnapshotRow,
    StatementSide,
    TxnKey,
    Verdict,
)

logger = logging.getLogger(__name__)


# ---- evidence shapes (written to the database by repository.create_comparison) ----------------


@dataclass(frozen=True)
class SideDraft:
    content_hash: str
    file_name: str | None
    bank_name: str | None
    period_start: date
    period_end: date
    transaction_count: int
    rows: tuple[SnapshotRow, ...]


@dataclass(frozen=True)
class ComparisonDraft:
    earlier: SideDraft
    later: SideDraft
    matched_count: int
    match_ratio: Decimal
    reason: str


@dataclass(frozen=True)
class DuplicateMatch:
    held: StatementSide
    verdict: Verdict  # computed as evaluate(held, incoming): a = held, b = incoming
    draft: ComparisonDraft


@dataclass(frozen=True)
class PairFinding:
    earlier: StatementSide
    later: StatementSide
    verdict: Verdict  # a = earlier, b = later
    draft: ComparisonDraft
    keep_hash: str
    remove_hash: str
    removal_allowed: bool
    corrections: dict[str, int]
    existing_status: DuplicatePairStatus | None  # the stored pair's status, if there is one

    @property
    def key(self) -> tuple[str, str]:
        return repository.pair_key(self.earlier.content_hash, self.later.content_hash)


@dataclass(frozen=True)
class NearMiss:
    earlier: StatementSide
    later: StatementSide
    why_not: str


def current_settings() -> DetectionSettings:
    return DetectionSettings.from_worker_settings(config.settings)


# ---- building sides and evidence --------------------------------------------------------------


def side_from_extracted(extracted, content_hash: str, file_name: str | None) -> StatementSide | None:
    """The incoming file as a matcher input, or None when it cannot be compared (no bank name,
    or no transactions)."""
    if not extracted.bank_name:
        return None
    txns: list[TxnKey] = []
    facts: list[AccountFact] = []
    for section in extracted.sections:
        currency = section.currency or extracted.currency
        for t in section.transactions:
            txns.append(TxnKey(t.transaction_date, t.amount, t.direction.value, currency, t.description))
        identifier = normalize_identifier(section.account_identifier)
        if identifier is not None:
            facts.append(AccountFact(identifier, currency, section.closing_balance, section.closing_balance_date))
    if not txns:
        return None
    return StatementSide(
        content_hash=content_hash,
        bank_key=bank_key(extracted.bank_name),
        transactions=tuple(txns),
        accounts=tuple(facts),
        bank_name=extracted.bank_name,
        file_name=file_name,
    )


def _side_draft(side: StatementSide, matched: set[int]) -> SideDraft:
    period = side.period
    return SideDraft(
        content_hash=side.content_hash,
        file_name=side.file_name,
        bank_name=side.bank_name,
        period_start=period[0],
        period_end=period[1],
        transaction_count=len(side.transactions),
        rows=tuple(matching.select_snapshot(side.transactions, matched)),
    )


def build_comparison_draft(verdict: Verdict, earlier: StatementSide, later: StatementSide, *, incoming: bool) -> ComparisonDraft:
    """`verdict` must have been computed as evaluate(earlier, later): index a is the earlier side."""
    matched_earlier = {i for i, _ in verdict.matched_pairs}
    matched_later = {j for _, j in verdict.matched_pairs}
    return ComparisonDraft(
        earlier=_side_draft(earlier, matched_earlier),
        later=_side_draft(later, matched_later),
        matched_count=verdict.matched_count,
        match_ratio=verdict.ratio,
        reason=matching.describe(verdict, earlier, later, incoming=incoming),
    )


# ---- check 2: judge an extracted statement -----------------------------------------------------


def find_probable_duplicate_of(
    db: Session,
    extracted,
    content_hash: str,
    *,
    file_name: str | None = None,
    force_enabled: bool = False,
) -> DuplicateMatch | None:
    """WR-59: is this extracted file probably the same statement as one already held? Read-only.

    Returns None when detection is off (unless `force_enabled`, used by the Backfill Tool), the file
    was overridden, it cannot be compared, or no held statement is a probable duplicate."""
    settings = current_settings()
    if not (settings.enabled or force_enabled):
        return None
    if content_hash in repository.overridden_hashes(db):
        return None
    incoming = side_from_extracted(extracted, content_hash, file_name)
    if incoming is None:
        return None

    period = incoming.period
    dismissed = repository.dismissed_pair_keys(db)
    candidates = [
        s
        for s in repository.load_summaries(db)
        if s.bank_key == incoming.bank_key
        and s.content_hash != content_hash
        and matching.periods_overlap(s.period, period)
        and repository.pair_key(s.content_hash, content_hash) not in dismissed
    ]
    best: tuple[tuple, StatementSide, Verdict] | None = None
    for held in repository.load_sides(db, candidates):
        verdict = matching.evaluate(held, incoming, settings)
        if not verdict.is_duplicate:
            continue
        rank = (-verdict.matched_count, held.ingested_at)
        if best is None or rank < best[0]:
            best = (rank, held, verdict)
    if best is None:
        return None
    _, held, verdict = best
    return DuplicateMatch(held, verdict, build_comparison_draft(verdict, held, incoming, incoming=True))


def record_skipped_duplicate(db: Session, match: DuplicateMatch, content_hash: str):
    """WR-62: write the comparison and the `probable_duplicate` remembered file. Nothing else is
    written, so a skipped file creates no statement, section, transaction or account. Returns the
    comparison."""
    comparison = repository.create_comparison(db, match.draft)
    repository.insert_known_file(
        db,
        content_hash=content_hash,
        state=KnownFileState.PROBABLE_DUPLICATE,
        matched_hash=match.held.content_hash,
        comparison_id=comparison.id,
    )
    return comparison


# ---- the pair scan ------------------------------------------------------------------------------


def _ordered(a: StatementSide, b: StatementSide) -> tuple[StatementSide, StatementSide]:
    """(earlier-ingested, later-ingested); ties by smaller content hash."""
    ka = (a.ingested_at, a.content_hash)
    kb = (b.ingested_at, b.content_hash)
    return (a, b) if ka <= kb else (b, a)


def compute_findings(db: Session, settings: DetectionSettings) -> tuple[list[PairFinding], list[NearMiss]]:
    """Apply the rule to every pair of held statements. Writes nothing. Pairs with an overridden
    file on either side are excluded; each finding carries the stored pair's status if there is one,
    so callers can leave dismissed, removed and superseded pairs alone (BR-44)."""
    overridden = repository.overridden_hashes(db)
    existing = repository.load_pairs(db)
    summaries = [s for s in repository.load_summaries(db) if s.bank_name and s.content_hash not in overridden]
    sides = {s.content_hash: side for s, side in zip(summaries, repository.load_sides(db, summaries), strict=True)}

    by_bank: dict[str, list[StatementSide]] = {}
    for side in sides.values():
        by_bank.setdefault(side.bank_key, []).append(side)

    raw: list[tuple[StatementSide, StatementSide, Verdict]] = []
    near: list[NearMiss] = []
    for group in by_bank.values():
        for x, y in combinations(group, 2):
            if not matching.periods_overlap(x.period, y.period):
                continue
            earlier, later = _ordered(x, y)
            verdict = matching.evaluate(earlier, later, settings)
            if verdict.is_duplicate:
                raw.append((earlier, later, verdict))
            elif verdict.is_candidate:
                near.append(NearMiss(earlier, later, verdict.why_not or "not flagged"))

    corrections = repository.manual_correction_counts(db, sorted({h for e, la, _ in raw for h in (e.content_hash, la.content_hash)}))
    findings = []
    for earlier, later, verdict in raw:
        keep, remove = matching.choose_kept_copy(
            CopyFacts(earlier.content_hash, corrections[earlier.content_hash], earlier.ingested_at),
            CopyFacts(later.content_hash, corrections[later.content_hash], later.ingested_at),
        )
        key = repository.pair_key(earlier.content_hash, later.content_hash)
        stored = existing.get(key)
        findings.append(
            PairFinding(
                earlier=earlier,
                later=later,
                verdict=verdict,
                draft=build_comparison_draft(verdict, earlier, later, incoming=False),
                keep_hash=keep.content_hash,
                remove_hash=remove.content_hash,
                removal_allowed=verdict.sizes_comparable,
                corrections={earlier.content_hash: corrections[earlier.content_hash], later.content_hash: corrections[later.content_hash]},
                existing_status=stored.status if stored is not None else None,
            )
        )
    return findings, near


def is_pair_scan_due_now(db: Session) -> bool:
    """WR-63."""
    settings = current_settings()
    if not settings.enabled:
        return False
    state = repository.get_scan_state(db)
    if state is None or state.last_scan_completed_at is None or state.last_scan_started_at is None:
        return True
    if state.last_scan_completed_at < state.last_scan_started_at:  # a scan began and never finished
        return True
    if state.last_scan_match_ratio is None or Decimal(state.last_scan_match_ratio) != settings.match_ratio.quantize(Decimal("0.0001")):
        return True
    if state.last_scan_min_transactions != settings.min_transactions:
        return True
    if state.recheck_requested_at is not None and state.recheck_requested_at > state.last_scan_started_at:
        return True
    latest = repository.latest_statement_time(db)
    return latest is not None and latest > state.last_scan_started_at


def run_pair_scan(db: Session) -> int:
    """WR-63 / WR-64: insert new pairs, refresh pending ones, supersede pending pairs that are no
    longer found (a statement gone, a file overridden, or no longer flagged under the current
    settings), and leave dismissed, removed and superseded pairs alone. Returns the number of pairs
    pending after the scan."""
    settings = current_settings()
    state = repository.get_or_create_scan_state(db)
    state.last_scan_started_at = datetime.now(UTC)
    state.last_scan_completed_at = None  # a scan that raises leaves this null, so it stays due
    db.flush()

    findings, _near = compute_findings(db, settings)
    stored = repository.load_pairs(db)
    found_keys = set()
    for finding in findings:
        found_keys.add(finding.key)
        pair = stored.get(finding.key)
        if pair is None:
            comparison = repository.create_comparison(db, finding.draft)
            repository.insert_pair(
                db,
                key=finding.key,
                comparison_id=comparison.id,
                keep_hash=finding.keep_hash,
                removal_allowed=finding.removal_allowed,
            )
        elif pair.status == DuplicatePairStatus.PENDING:
            pair.keep_hash = finding.keep_hash
            pair.removal_allowed = finding.removal_allowed
    for key, pair in stored.items():
        if pair.status == DuplicatePairStatus.PENDING and key not in found_keys:
            repository.supersede_pair(db, pair)
    db.flush()

    pending = sum(1 for p in repository.load_pairs(db).values() if p.status == DuplicatePairStatus.PENDING)
    state.last_scan_completed_at = datetime.now(UTC)
    state.last_scan_match_ratio = settings.match_ratio.quantize(Decimal("0.0001"))
    state.last_scan_min_transactions = settings.min_transactions
    state.last_scan_pairs_found = pending
    db.flush()
    logger.info("Duplicate scan complete: %d pair(s) awaiting a decision", pending)
    return pending
