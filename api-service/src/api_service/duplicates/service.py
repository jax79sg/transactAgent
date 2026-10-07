"""Duplicate Review business logic (functional-design AR-38..AR-50, Epic 14).

Dumb on purpose, like the recategorization review: it reads what the Ingestion Worker wrote and records
the user's decisions. It never decides whether two statements match, never recomputes the worker's keep
proposal or `removal_allowed`, never calls the worker, and never touches the vector store. Removal is
requested by inserting a job row that the worker executes.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from transactagent_db.models import (
    DuplicateComparison,
    DuplicatePair,
    DuplicatePairStatus,
    KnownFile,
    KnownFileState,
    StatementRemovalJob,
)

from api_service.app_settings import service as settings_service
from api_service.duplicates import repository
from api_service.duplicates.schemas import (
    ComparisonDTO,
    ComparisonRowDTO,
    ComparisonSideDTO,
    OverrideResponse,
    PairDTO,
    PairPage,
    RemovalPreviewDTO,
    RemovalRequest,
    RemovalStatusDTO,
    ScanStatusDTO,
    StatementLabelDTO,
)
from api_service.errors import (
    ConfirmationOutOfDateError,
    NotASkippedFileError,
    NotFoundError,
    PairNotPendingError,
    RemovalAlreadyRequestedError,
    RemovalNotOfferedError,
    StatementMissingError,
)

RECENTLY_REMOVED_WINDOW = timedelta(hours=24)  # AR-39
_REMOVED_COPY_NOTE = (
    "This file will be ingested on the next ingestion run. The manual corrections that sat on the "
    "removed copy are not restored."
)


def _now() -> datetime:
    return datetime.now(UTC)


# ---- labels -------------------------------------------------------------------------------------


def _side_label(comparison: DuplicateComparison, side: str) -> StatementLabelDTO:
    return StatementLabelDTO(
        content_hash=getattr(comparison, f"{side}_content_hash"),
        file_name=getattr(comparison, f"{side}_file_name"),
        bank_name=getattr(comparison, f"{side}_bank_name"),
        period_start=getattr(comparison, f"{side}_period_start"),
        period_end=getattr(comparison, f"{side}_period_end"),
        transaction_count=getattr(comparison, f"{side}_transaction_count"),
    )


def label_for_hash(comparison: DuplicateComparison, content_hash: str) -> StatementLabelDTO:
    """The comparison side with this content hash (falling back to the earlier side, which cannot happen
    for a well-formed pair: a pair's hashes are its comparison's two hashes)."""
    return _side_label(comparison, "later" if comparison.later_content_hash == content_hash else "earlier")


def _other_hash(pair: DuplicatePair, content_hash: str) -> str:
    return pair.hash_b if content_hash == pair.hash_a else pair.hash_a


# ---- pairs --------------------------------------------------------------------------------------


def _removal_status(job: StatementRemovalJob | None) -> RemovalStatusDTO | None:
    if job is None:
        return None
    return RemovalStatusDTO(
        job_id=job.id,
        status=job.status.value,
        failure_reason=job.failure_reason,
        requested_at=job.requested_at,
        finished_at=job.finished_at,
        deleted_counts=job.deleted_counts,
    )


def build_pair(db: Session, pair: DuplicatePair) -> PairDTO:
    """AR-41: labels from the stored comparison; the worker's keep proposal and `removal_allowed`
    displayed as stored; live manual-correction counts and the preview read now."""
    comparison = repository.get_comparison(db, pair.comparison_id)
    remove_hash = _other_hash(pair, pair.keep_hash)
    keep, remove = label_for_hash(comparison, pair.keep_hash), label_for_hash(comparison, remove_hash)
    ids = repository.statement_ids_by_hash(db, [pair.keep_hash, remove_hash])
    job = repository.latest_job(db, pair.id)
    active = repository.has_active_job(db, pair.id)
    pending = pair.status == DuplicatePairStatus.PENDING
    stale = pending and len(ids) < 2

    corrections_kept = repository.manual_corrections(db, ids[pair.keep_hash]) if pair.keep_hash in ids else None
    corrections_removed = repository.manual_corrections(db, ids[remove_hash]) if remove_hash in ids else None
    offered = pending and pair.removal_allowed and not stale and not active

    preview = None
    if offered:
        counts = repository.preview_counts(db, ids[remove_hash])
        preview = RemovalPreviewDTO(
            **counts,
            corrections_lost=corrections_removed,
            # Matching is one-to-one, so the removed side's count minus the matched count is exactly the
            # number of its transactions with no match: the API needs no copy of the matching rule.
            only_on_removed_copy=max(0, remove.transaction_count - comparison.matched_count),
        )
    return PairDTO(
        id=pair.id,
        comparison_id=pair.comparison_id,
        status=pair.status.value,
        removal_offered=offered,
        stale=stale,
        keep=keep,
        remove=remove,
        corrections_on_kept=None if stale else corrections_kept,
        corrections_on_removed=None if stale else corrections_removed,
        preview=preview,
        removal=_removal_status(job),
        found_at=pair.found_at,
    )


def list_pairs(db: Session, page: int, page_size: int) -> PairPage:
    """AR-39: in-flight removals first, then pending pairs, then pairs removed in the last 24 hours;
    newest first within each group; paginated."""
    candidates = repository.list_candidate_pairs(db, removed_since=_now() - RECENTLY_REMOVED_WINDOW)

    def group(pair: DuplicatePair) -> int:
        if repository.has_active_job(db, pair.id):
            return 0
        return 1 if pair.status == DuplicatePairStatus.PENDING else 2

    ordered = sorted(candidates, key=lambda p: (group(p), -p.found_at.timestamp(), str(p.id)))
    window = ordered[(page - 1) * page_size : page * page_size]
    return PairPage(items=[build_pair(db, p) for p in window], page=page, page_size=page_size, total_count=len(ordered))


def get_pending_count(db: Session) -> int:
    """AR-40."""
    return repository.count_pending_without_active_job(db)


# ---- decisions ------------------------------------------------------------------------------------


def _pair_or_404(db: Session, pair_id: UUID) -> DuplicatePair:
    pair = repository.get_pair(db, pair_id)
    if pair is None:
        raise NotFoundError(f"Probable-duplicate pair {pair_id} not found")
    return pair


def confirm_removal(db: Session, pair_id: UUID, request: RemovalRequest) -> PairDTO:
    """AR-42: ordered checks, the first failure wins, then one `queued` job. Deletes nothing: the worker
    re-verifies and executes."""
    pair = _pair_or_404(db, pair_id)
    if pair.status != DuplicatePairStatus.PENDING:
        raise PairNotPendingError(f"This pair is no longer pending (it is {pair.status.value}).")
    if not pair.removal_allowed:
        raise RemovalNotOfferedError("Removal is not offered for this pair: the statements differ in size.")
    if repository.has_active_job(db, pair.id):
        raise RemovalAlreadyRequestedError("A removal for this pair is already in progress.")

    remove_hash = _other_hash(pair, pair.keep_hash)
    ids = repository.statement_ids_by_hash(db, [pair.keep_hash, remove_hash])
    if len(ids) < 2:
        raise StatementMissingError("One of these statements no longer exists, so nothing can be removed.")
    if request.remove_statement_hash != remove_hash:
        raise ConfirmationOutOfDateError("The copy proposed for removal has changed since you looked. Please review again.")
    live = repository.manual_corrections(db, ids[remove_hash])
    if live != request.acknowledged_corrections_lost:
        raise ConfirmationOutOfDateError(
            f"The manual corrections on this copy changed from {request.acknowledged_corrections_lost} to {live} "
            "since you looked. Please review again."
        )

    try:
        with db.begin_nested():  # a lost race (BR-45's one-active-job rule) must not poison the session
            db.add(
                StatementRemovalJob(
                    pair_id=pair.id, remove_statement_hash=remove_hash, corrections_acknowledged=live
                )
            )
            db.flush()
    except IntegrityError as exc:
        raise RemovalAlreadyRequestedError("A removal for this pair is already in progress.") from exc
    return build_pair(db, pair)


def dismiss_pair(db: Session, pair_id: UUID) -> PairDTO:
    """AR-43: a single conditional write, so a concurrent scan refresh cannot overwrite the decision."""
    pair = _pair_or_404(db, pair_id)
    if repository.has_active_job(db, pair.id):
        raise RemovalAlreadyRequestedError("A removal for this pair is already in progress.")
    result = db.execute(
        update(DuplicatePair)
        .where(DuplicatePair.id == pair_id, DuplicatePair.status == DuplicatePairStatus.PENDING)
        .values(status=DuplicatePairStatus.DISMISSED, decided_at=_now())
    )
    if result.rowcount == 0:
        db.refresh(pair)
        raise PairNotPendingError(f"This pair is no longer pending (it is {pair.status.value}).")
    db.refresh(pair)
    return build_pair(db, pair)


# ---- comparisons ----------------------------------------------------------------------------------


def remembered_file(db: Session, comparison: DuplicateComparison) -> KnownFile | None:
    hashes = {comparison.earlier_content_hash, comparison.later_content_hash}
    for known in repository.known_files_for_comparison(db, comparison.id):
        if known.pdf_content_hash in hashes:
            return known
    return None


def _overridden_state(db: Session, known: KnownFile) -> str:
    return "ingested_at_your_request" if repository.statement_exists(db, known.pdf_content_hash) else "ingest_at_next_run"


def get_comparison(db: Session, comparison_id: UUID) -> ComparisonDTO:
    """AR-45: the stored snapshot plus a derived state. Unchanged if the original later changes."""
    comparison = repository.get_comparison(db, comparison_id)
    if comparison is None:
        raise NotFoundError(f"Comparison {comparison_id} not found")

    known = remembered_file(db, comparison)
    pair = None if known is not None else repository.pair_for_comparison(db, comparison.id)
    this_file_side = None
    pair_id = None
    removal_offered = None
    if known is not None:
        this_file_side = "earlier" if known.pdf_content_hash == comparison.earlier_content_hash else "later"
        state = {
            KnownFileState.PROBABLE_DUPLICATE: "skipped",
            KnownFileState.CONFIRMED_DUPLICATE: "removed",
        }.get(known.state) or _overridden_state(db, known)
    elif pair is not None:
        pair_id = pair.id
        removal_offered = bool(
            pair.status == DuplicatePairStatus.PENDING and pair.removal_allowed and not repository.has_active_job(db, pair.id)
        )
        state = {
            DuplicatePairStatus.PENDING: "pair_pending",
            DuplicatePairStatus.DISMISSED: "pair_dismissed",
            DuplicatePairStatus.REMOVED: "removed",
            DuplicatePairStatus.SUPERSEDED: "pair_superseded",
        }[pair.status]
    else:
        state = "pair_superseded"  # evidence with no record pointing at it any more

    def side(name: str) -> ComparisonSideDTO:
        rows = sorted((r for r in comparison.rows if r.side.value == name), key=lambda r: r.rank)
        return ComparisonSideDTO(
            label=_side_label(comparison, name),
            rows=[
                ComparisonRowDTO(
                    rank=r.rank,
                    transaction_date=r.transaction_date,
                    description=r.description,
                    out_flow=r.out_flow,
                    in_flow=r.in_flow,
                    currency=r.currency,
                    marker=r.marker.value,
                )
                for r in rows
            ],
        )

    return ComparisonDTO(
        id=comparison.id,
        state=state,
        reason=comparison.reason,
        matched_count=comparison.matched_count,
        match_ratio=comparison.match_ratio,
        earlier=side("earlier"),
        later=side("later"),
        this_file_side=this_file_side,
        can_override=known is not None and known.state in (KnownFileState.PROBABLE_DUPLICATE, KnownFileState.CONFIRMED_DUPLICATE),
        pair_id=pair_id,
        removal_offered=removal_offered,
        created_at=comparison.created_at,
    )


def override_skipped_file(db: Session, comparison_id: UUID) -> OverrideResponse:
    """AR-44: "Not a duplicate -- ingest it". Idempotent; takes effect on the NEXT ingestion run."""
    comparison = repository.get_comparison(db, comparison_id)
    if comparison is None:
        raise NotFoundError(f"Comparison {comparison_id} not found")
    known = remembered_file(db, comparison)
    if known is None:
        raise NotASkippedFileError("This comparison belongs to a pair of stored statements, not to a skipped file.")
    note = None
    if known.state != KnownFileState.OVERRIDDEN:
        if known.state == KnownFileState.CONFIRMED_DUPLICATE:
            note = _REMOVED_COPY_NOTE
        known.state = KnownFileState.OVERRIDDEN
        known.decided_at = _now()
        db.flush()
    return OverrideResponse(comparison_id=comparison.id, state=_overridden_state(db, known), note=note)


# ---- scan status ----------------------------------------------------------------------------------


def get_scan_status(db: Session) -> ScanStatusDTO:
    """AR-46. `pairs_found` is how many pairs are flagged and undecided NOW, not the figure the last scan stored:
    the panel prints it beside the list, and after a pair is dismissed or removed a frozen "1 found" would sit next
    to "No probable duplicate statements." (found by the cross-service scenario at Build and Test, 2026-10-04)."""
    state = repository.get_scan_state(db)
    enabled = settings_service.get_setting("duplicate_detection_enabled")["value"] == "true"
    if state is None:
        return ScanStatusDTO(last_completed_at=None, pairs_found=None, recheck_requested=False, detection_enabled=enabled)
    recheck = state.recheck_requested_at is not None and (
        state.last_scan_started_at is None or state.recheck_requested_at > state.last_scan_started_at
    )
    return ScanStatusDTO(
        last_completed_at=state.last_scan_completed_at,
        pairs_found=repository.count_pending(db) if state.last_scan_completed_at is not None else None,
        recheck_requested=recheck,
        detection_enabled=enabled,
    )


def request_recheck(db: Session) -> ScanStatusDTO:
    """AR-46: only a request; the worker acts on it at its next due check. Idempotent."""
    repository.get_or_create_scan_state(db).recheck_requested_at = _now()
    db.flush()
    return get_scan_status(db)
