"""Categorization orchestration (business-logic-model.md — Categorization Engine
Component). Implements the FR-5.2 fallback chain and the FR-5.4/WR-5 retroactive
re-scan.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from ingestion_worker.categorization import llm_classifier, repository
from ingestion_worker.categorization.similarity import (
    SimilarityCandidate,
    SimilarityMatch,
    amounts_in_range,
    find_best_match,
    select_best_match,
)
from ingestion_worker.config import settings
from ingestion_worker.embedding import client as embedding_client
from ingestion_worker.embedding import text as embedding_text
from ingestion_worker.embedding import vector_store
from ingestion_worker.embedding.similarity import cosine_similarity
from transactagent_db.models import (
    CategorySource,
    RecategorizationProposalSourceBucket,
    RecategorizationProposalStatus,
)

UNSURE_NAME = "UNSURE"


def _chunk(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def classify_batch(db: Session, descriptions: list[str]) -> dict[str, str]:
    """WR-27 (Matching Precision Refinement, revised after live testing against a
    real local model server showed one HTTP call per transaction was too many
    round-trips for a large statement): every transaction gets classified by the
    LLM, always -- called once per file by the Orchestrator, upfront, before the
    per-transaction persistence loop begins (Application Design Key Design
    Resolution 2).

    Two phases:
    1. Descriptions are de-duplicated, chunked into groups of
       `llm_classification_batch_size`, and each chunk is classified in a single
       prompt/response (`llm_classifier.classify_batch_prompt`) -- chunks run
       concurrently, bounded by `llm_classification_concurrency` (NFR-MPR-1), so at
       most `concurrency` HTTP requests are in flight at once regardless of how
       many transactions are in the file.
    2. Any description the batch phase didn't return a value for (a parse failure,
       a too-short response, or an individual entry that wasn't a valid whitelist
       name/UNSURE -- see `classify_batch_prompt`'s docstring) falls back to an
       individual `classify()` call -- also concurrent, also bounded by the same
       cap. Only the specific unparseable descriptions redo work, not the whole
       batch they were part of.

    Returns a value in the whitelist or the literal UNSURE for every unique
    description given -- llm_classifier's existing WR-4 "never raises" contract,
    unchanged."""
    unique_descriptions = list(dict.fromkeys(descriptions))
    if not unique_descriptions:
        return {}
    whitelist = [name for name in repository.list_active_category_names(db) if name != UNSURE_NAME]

    results: dict[str, str] = {}
    chunks = _chunk(unique_descriptions, settings.llm_classification_batch_size)
    with ThreadPoolExecutor(max_workers=settings.llm_classification_concurrency) as executor:
        futures = [executor.submit(llm_classifier.classify_batch_prompt, chunk, whitelist) for chunk in chunks]
        for future in as_completed(futures):
            results.update(future.result())

    missing = [description for description in unique_descriptions if description not in results]
    if missing:
        with ThreadPoolExecutor(max_workers=settings.llm_classification_concurrency) as executor:
            future_to_description = {
                executor.submit(llm_classifier.classify, description, whitelist): description
                for description in missing
            }
            for future in as_completed(future_to_description):
                description = future_to_description[future]
                results[description] = future.result()

    return results


def _boosted_score(raw_score: float, candidate_category_name: str, llm_category: str | None) -> float:
    """WR-30: a small boost when the candidate's known category agrees with the
    given LLM classification -- never a penalty on disagreement, only a boost
    withheld. Capped at 1.0 (the cosine scale's own ceiling)."""
    if llm_category and llm_category != UNSURE_NAME and candidate_category_name == llm_category:
        return min(1.0, raw_score + settings.embedding_llm_agreement_boost)
    return raw_score


def find_similar_transaction_via_embedding(
    db: Session, description: str, amount: Decimal, llm_category: str | None = None
) -> SimilarityMatch | None:
    """WR-21/22/23 (Epic 9): tried before the fuzzy-text fallback, both by
    `categorize()` below and, via a separate pairwise variant inlined in
    `recategorize_unsure_from_precedent`, the retroactive re-scan. Searches the
    `transactions` vector-store collection -- only already-embedded historical
    transactions are findable this way; a brand-new transaction's own embedding
    hasn't been computed yet (Application Design's "Key Design Resolution":
    query-time search is always against already-stored candidates, storage-time
    embedding of the transaction itself is a separate, async concern owned by
    `embedding/service.py`).

    A matched candidate's `.score` is rescaled to the same 0-100 range
    `find_best_match`'s fuzzy scores use (`cosine_similarity * 100`) -- callers and
    downstream consumers (e.g. `recategorization_auto_apply_threshold`,
    `RecategorizationProposal.match_score`) compare/store this value on that scale
    throughout the rest of this codebase; only the *eligibility* check against
    `embedding_similarity_threshold` uses the raw 0.0-1.0 cosine value, since that
    threshold is itself expressed on the embedding scale.

    `llm_category` (Matching Precision Refinement, WR-29/30): when given, (1) the
    embedded query text includes the price-range bucket alongside `description`
    (WR-29), and (2) a candidate whose actual category agrees with `llm_category`
    gets a small score boost before the threshold check (WR-30) -- the same
    always-on LLM classification `categorize()` below already computed for this same
    transaction, passed through rather than recomputed.
    """
    vector = embedding_client.compute_embedding(embedding_text.build_embedding_text(description, amount))
    if vector is None:
        return None
    neighbors = vector_store.query_nearest_neighbors(
        vector, collection=vector_store.TRANSACTIONS_COLLECTION, top_k=settings.embedding_top_k
    )
    if not neighbors:
        return None
    candidates_by_id = repository.get_similarity_candidates_by_ids(db, [entity_id for entity_id, _ in neighbors])
    scored = []
    for entity_id, score in neighbors:
        candidate = candidates_by_id.get(entity_id)
        if candidate is None:
            continue  # stale vector-store entry (e.g. a deleted transaction) -- skip, not an error
        boosted_score = _boosted_score(score, candidate.category_name, llm_category)
        if boosted_score < settings.embedding_similarity_threshold:
            continue
        if not amounts_in_range(
            amount,
            candidate.amount,
            ratio_tolerance=settings.similarity_amount_ratio_tolerance,
            absolute_floor=Decimal(str(settings.similarity_amount_absolute_floor)),
        ):
            continue
        scored.append(SimilarityMatch(candidate=candidate, score=round(boosted_score * 100, 2)))
    return select_best_match(scored)


@dataclass(frozen=True)
class DisagreementInfo:
    """Matching Precision Refinement: carries a genuine disagreement (WR-28) forward
    from `categorize()` to the Orchestrator, which records the `CategorizationDisagreement`
    row only after the new transaction has a real id (domain-entities.md)."""

    similarity_category_name: str
    llm_category_name: str
    similarity_score: float


@dataclass
class CategorizationResult:
    category_name: str
    source: str  # "similarity" | "llm" | "unsure"
    matched_precedent_transaction_id: str | None = None
    llm_suggested_category_name: str | None = None  # None = LLM abstained/unavailable (WR-28)
    disagreement: DisagreementInfo | None = None


def _transaction_amount(txn) -> Decimal:
    """out_flow or in_flow, whichever is set (BR-2: exactly one always is) -- see
    repository.list_similarity_candidates's docstring for why only magnitude matters."""
    return txn.out_flow if txn.out_flow is not None else txn.in_flow


def categorize(db: Session, description: str, amount: Decimal, llm_category: str) -> CategorizationResult:
    """FR-5.2 fallback chain, refined by WR-27/28 (Matching Precision Refinement):
    `llm_category` is the always-on LLM classification, already computed upfront for
    the whole file by `classify_batch` -- no longer computed here as a last resort.

    Decision (WR-28): similarity and LLM agree -> auto-assign; only one is
    confident (the other abstained/found nothing) -> that one wins directly, not a
    disagreement; both confident and differing -> genuine disagreement, neither
    auto-assigned, recorded via `disagreement` for the caller to persist.
    """
    match = find_similar_transaction_via_embedding(db, description, amount, llm_category)
    if match is None:
        candidates = repository.list_similarity_candidates(db)
        match = find_best_match(
            description,
            amount,
            candidates,
            threshold=settings.similarity_threshold,
            amount_ratio_tolerance=settings.similarity_amount_ratio_tolerance,
            amount_absolute_floor=Decimal(str(settings.similarity_amount_absolute_floor)),
        )

    similarity_category = match.candidate.category_name if match is not None else None
    llm_confident = llm_category is not None and llm_category != UNSURE_NAME
    llm_suggested_name = llm_category if llm_confident else None

    if similarity_category is not None and llm_confident:
        if similarity_category == llm_category:
            return CategorizationResult(
                category_name=similarity_category,
                source="similarity",
                matched_precedent_transaction_id=match.candidate.transaction_id,
                llm_suggested_category_name=llm_suggested_name,
            )
        return CategorizationResult(
            category_name=UNSURE_NAME,
            source="unsure",
            llm_suggested_category_name=llm_suggested_name,
            disagreement=DisagreementInfo(
                similarity_category_name=similarity_category,
                llm_category_name=llm_category,
                similarity_score=match.score,
            ),
        )
    if similarity_category is not None:
        return CategorizationResult(
            category_name=similarity_category,
            source="similarity",
            matched_precedent_transaction_id=match.candidate.transaction_id,
            llm_suggested_category_name=llm_suggested_name,
        )
    if llm_confident:
        return CategorizationResult(category_name=llm_category, source="llm", llm_suggested_category_name=llm_suggested_name)
    return CategorizationResult(category_name=UNSURE_NAME, source="unsure", llm_suggested_category_name=None)


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

    # WR-21 (Epic 9): computed once, reused for every candidate this job considers
    # -- source_transaction never changes within one re-scan. A direct pairwise
    # comparison, not a vector-store search: this re-scan only ever has ONE
    # candidate to check each transaction against (source_transaction itself), so
    # there's no "nearest neighbors among many" to search for.
    # WR-29 (Matching Precision Refinement): price-bucketed text, not raw description.
    source_vector = embedding_client.compute_embedding(
        embedding_text.build_embedding_text(source_transaction.description, _transaction_amount(source_transaction))
    )

    def _find_match(candidate_txn) -> SimilarityMatch | None:
        if source_vector is not None:
            candidate_vector = embedding_client.compute_embedding(
                embedding_text.build_embedding_text(candidate_txn.description, _transaction_amount(candidate_txn))
            )
            if candidate_vector is not None:
                cosine_score = cosine_similarity(source_vector, candidate_vector)
                # WR-30: boost when the CANDIDATE's own persisted LLM classification
                # (set back when it was originally ingested, WR-28) agrees with the
                # category being PROPOSED (source_transaction's corrected category) --
                # the candidate's independent LLM opinion, read back later, either
                # corroborates or doesn't corroborate this re-categorization.
                candidate_llm_category = (
                    candidate_txn.llm_suggested_category.name if candidate_txn.llm_suggested_category_id else None
                )
                cosine_score = _boosted_score(cosine_score, source_transaction.category.name, candidate_llm_category)
                if cosine_score >= settings.embedding_similarity_threshold and amounts_in_range(
                    _transaction_amount(candidate_txn),
                    _transaction_amount(source_transaction),
                    ratio_tolerance=amount_ratio_tolerance,
                    absolute_floor=amount_absolute_floor,
                ):
                    # Rescaled to the 0-100 scale, same reasoning as
                    # find_similar_transaction_via_embedding above.
                    return SimilarityMatch(candidate=source_candidate, score=round(cosine_score * 100, 2))
        return find_best_match(
            candidate_txn.description,
            _transaction_amount(candidate_txn),
            [source_candidate],
            threshold=settings.similarity_threshold,
            amount_ratio_tolerance=amount_ratio_tolerance,
            amount_absolute_floor=amount_absolute_floor,
        )

    for unsure_txn in repository.find_unsure_transactions(db):
        match = _find_match(unsure_txn)
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
        match = _find_match(candidate_txn)
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
