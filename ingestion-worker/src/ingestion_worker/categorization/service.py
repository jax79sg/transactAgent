"""Categorization orchestration (business-logic-model.md — Categorization Engine
Component). Implements the FR-5.2 fallback chain and the FR-5.4/WR-5 retroactive
re-scan.
"""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from ingestion_worker.categorization import llm_classifier, repository
from ingestion_worker.categorization.similarity import SimilarityCandidate, find_best_match
from ingestion_worker.config import settings
from transactagent_db.models import (
    CategorySource,
    RecategorizationProposalSourceBucket,
    RecategorizationProposalStatus,
)

UNSURE_NAME = "UNSURE"


@dataclass
class CategorizationResult:
    category_name: str
    source: str  # "similarity" | "llm" | "unsure"
    matched_precedent_transaction_id: str | None = None


def _transaction_amount(txn) -> Decimal:
    """out_flow or in_flow, whichever is set (BR-2: exactly one always is) -- see
    repository.list_similarity_candidates's docstring for why only magnitude matters."""
    return txn.out_flow if txn.out_flow is not None else txn.in_flow


def categorize(db: Session, description: str, amount: Decimal) -> CategorizationResult:
    """FR-5.2 fallback chain: similarity match -> LLM fallback -> UNSURE."""
    candidates = repository.list_similarity_candidates(db)
    match = find_best_match(
        description,
        amount,
        candidates,
        threshold=settings.similarity_threshold,
        amount_ratio_tolerance=settings.similarity_amount_ratio_tolerance,
        amount_absolute_floor=Decimal(str(settings.similarity_amount_absolute_floor)),
    )
    if match is not None:
        return CategorizationResult(
            category_name=match.candidate.category_name,
            source="similarity",
            matched_precedent_transaction_id=match.candidate.transaction_id,
        )

    whitelist = [name for name in repository.list_active_category_names(db) if name != UNSURE_NAME]
    llm_answer = llm_classifier.classify(description, whitelist)
    if llm_answer == UNSURE_NAME:
        return CategorizationResult(category_name=UNSURE_NAME, source="unsure")
    return CategorizationResult(category_name=llm_answer, source="llm")


def recategorize_unsure_from_precedent(db: Session, job_id: UUID, source_transaction_id: UUID) -> list[UUID]:
    """FR-5.4 / WR-5, broadened by WR-9/WR-10 (Epic 6): similarity-only re-scan (no LLM
    call) of two candidate buckets against the newly-corrected transaction.

    UNSURE bucket (unchanged target set from WR-5): a match at/above the new, higher
    `recategorization_auto_apply_threshold` is applied directly, exactly as before
    (category_source='similarity', not 'manual' -- see business-logic-model.md note,
    preserves 'manual' as meaning a direct human edit on that exact row); a match
    at/above the existing similarity_threshold but below the auto-apply threshold
    becomes a pending RecategorizationProposal instead.

    Already-categorized bucket (new, WR-9): any match at/above similarity_threshold
    becomes a pending proposal -- this bucket never auto-applies, regardless of score
    (WR-10), since it would silently overwrite an existing categorization decision.

    Returns only the auto-applied transaction IDs -- this is what
    RecategorizationJob.updated_transaction_count has always meant; pending-proposal
    counts are queried directly from recategorization_proposals, not duplicated here.
    """
    source_transaction = repository.get_transaction(db, source_transaction_id)
    if source_transaction is None or source_transaction.category_source != CategorySource.MANUAL:
        # WR-11 (Unit 1): only manual corrections are precedent-worthy; defensive no-op
        # if called for anything else (shouldn't happen given AR-10 in Unit 2).
        return []

    # This is a targeted re-scan against the one specific corrected transaction, not
    # the whole precedent pool (list_similarity_candidates is used elsewhere in this
    # module for the general fallback chain, not here).
    source_candidate = SimilarityCandidate(
        transaction_id=str(source_transaction.id),
        description=source_transaction.description,
        category_name=source_transaction.category.name,
        category_source="manual",
        amount=_transaction_amount(source_transaction),
    )
    proposed_category = repository.find_category_by_name(db, source_transaction.category.name)
    if proposed_category is None:
        return []

    amount_ratio_tolerance = settings.similarity_amount_ratio_tolerance
    amount_absolute_floor = Decimal(str(settings.similarity_amount_absolute_floor))
    auto_applied_ids: list[UUID] = []

    for unsure_txn in repository.find_unsure_transactions(db):
        match = find_best_match(
            unsure_txn.description,
            _transaction_amount(unsure_txn),
            [source_candidate],
            threshold=settings.similarity_threshold,
            amount_ratio_tolerance=amount_ratio_tolerance,
            amount_absolute_floor=amount_absolute_floor,
        )
        if match is None:
            continue
        if match.score >= settings.recategorization_auto_apply_threshold:
            unsure_txn.category_id = proposed_category.id
            unsure_txn.category_source = CategorySource.SIMILARITY
            auto_applied_ids.append(unsure_txn.id)
            repository.record_proposal(
                db,
                job_id=job_id,
                candidate_transaction_id=unsure_txn.id,
                proposed_category_id=proposed_category.id,
                match_score=match.score,
                source_bucket=RecategorizationProposalSourceBucket.UNSURE,
                status=RecategorizationProposalStatus.AUTO_APPLIED,
            )
        else:
            repository.record_proposal(
                db,
                job_id=job_id,
                candidate_transaction_id=unsure_txn.id,
                proposed_category_id=proposed_category.id,
                match_score=match.score,
                source_bucket=RecategorizationProposalSourceBucket.UNSURE,
                status=RecategorizationProposalStatus.PENDING,
            )

    for candidate_txn in repository.find_categorized_transactions_excluding(
        db, exclude_transaction_id=source_transaction.id, exclude_category_id=proposed_category.id
    ):
        match = find_best_match(
            candidate_txn.description,
            _transaction_amount(candidate_txn),
            [source_candidate],
            threshold=settings.similarity_threshold,
            amount_ratio_tolerance=amount_ratio_tolerance,
            amount_absolute_floor=amount_absolute_floor,
        )
        if match is None:
            continue
        repository.record_proposal(
            db,
            job_id=job_id,
            candidate_transaction_id=candidate_txn.id,
            proposed_category_id=proposed_category.id,
            match_score=match.score,
            source_bucket=RecategorizationProposalSourceBucket.CATEGORIZED,
            status=RecategorizationProposalStatus.PENDING,
        )

    db.flush()
    return auto_applied_ids
