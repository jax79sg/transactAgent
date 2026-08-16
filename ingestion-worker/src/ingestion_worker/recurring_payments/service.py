"""Recurring Payment Manager Component (Epic 8, business-logic-model.md).
`match_new_transaction` is called from the Orchestrator's per-transaction
persistence step (WR-16); `run_detection_scan` is poll_once()'s fourth,
lowest-priority branch (services.md addendum).
"""

import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from rapidfuzz import fuzz

from ingestion_worker.categorization.service import UNSURE_NAME
from ingestion_worker.categorization.similarity import amounts_in_range
from ingestion_worker.config import settings
from ingestion_worker.embedding import client as embedding_client
from ingestion_worker.embedding import text as embedding_text
from ingestion_worker.embedding import vector_store
from ingestion_worker.embedding.similarity import cosine_similarity
from ingestion_worker.recurring_payments import cycle, repository
from transactagent_db.models import RecurringPayment, RecurringPaymentMatchStatus, Transaction

logger = logging.getLogger(__name__)


def _transaction_amount(transaction: Transaction) -> Decimal:
    return transaction.out_flow if transaction.out_flow is not None else transaction.in_flow


def _embedding_candidate_scores(description: str, amount: Decimal) -> dict[UUID, float] | None:
    """WR-21/22 (Epic 9), WR-29/30 (Matching Precision Refinement): searches the
    `recurring_payment_names` vector-store collection using price-bucketed query
    text (WR-29). Returns raw (unboosted, unfiltered-by-threshold) cosine scores
    keyed by payment id -- the boost (WR-30, category-agreement-aware) and the
    threshold check both need each candidate `RecurringPayment`'s own `.category`,
    which only `match_new_transaction`'s own loop below already has (avoids a
    second DB round-trip here just to fetch it again).

    Returns `None` (not an empty dict) both when the embedding path is entirely
    unusable (endpoint down) AND when it ran successfully but found zero neighbors
    at all -- both cases mean the same thing to the caller: fall back to the
    fuzzy-text check for every payment (WR-21 step 4 is a whole-operation fallback,
    not a per-payment one)."""
    vector = embedding_client.compute_embedding(embedding_text.build_embedding_text(description, amount))
    if vector is None:
        return None
    neighbors = vector_store.query_nearest_neighbors(
        vector, collection=vector_store.RECURRING_PAYMENT_NAMES_COLLECTION, top_k=settings.embedding_top_k
    )
    if not neighbors:
        return None
    return {UUID(entity_id): score for entity_id, score in neighbors}


def match_new_transaction(db, transaction: Transaction) -> None:
    """WR-16: candidate selection never gates on amount (expected_amount is a loose
    guide, FR-5) -- only the trust/tolerance decision (WR-18) is amount-aware."""
    amount = _transaction_amount(transaction)
    embedding_candidate_scores = _embedding_candidate_scores(transaction.description, amount)
    # WR-30: the transaction's own LLM classification is already known (WR-27/28,
    # computed and persisted before match_new_transaction is ever called).
    llm_category = transaction.llm_suggested_category.name if transaction.llm_suggested_category_id else None

    for payment in repository.list_recurring_payments(db):
        instance = cycle.nearest_due_date_instance(
            payment.frequency, payment.due_month, payment.due_day, transaction.transaction_date
        )
        if abs((transaction.transaction_date - instance).days) > settings.recurring_payment_match_window_days:
            continue  # outside the due-date matching window entirely

        cycle_period = cycle.cycle_period_for(payment.frequency, instance)  # WR-17
        if repository.has_live_match(db, payment.id, cycle_period):
            continue  # this cycle already has a pending/approved/auto_applied match

        if embedding_candidate_scores is not None:
            raw_score = embedding_candidate_scores.get(payment.id)
            if raw_score is None:
                matched = False
            else:
                boosted_score = raw_score
                if llm_category and llm_category != UNSURE_NAME and payment.category and payment.category.name == llm_category:
                    boosted_score = min(1.0, raw_score + settings.embedding_llm_agreement_boost)
                matched = boosted_score >= settings.embedding_similarity_threshold
        else:
            # Transaction descriptions are bank-statement text (typically all-caps);
            # a user-entered payment name (e.g. "Gym Membership") is mixed-case.
            # rapidfuzz's token_sort_ratio is case-sensitive, unlike this project's
            # other similarity call site (find_best_match), which never hits this
            # mismatch since it only ever compares two transaction descriptions
            # against each other -- both already bank-statement-cased. Caught by
            # actually running a match with realistic mixed-case input (score 18.75
            # vs. 87.5 for the same pair, case-normalized).
            score = fuzz.token_sort_ratio(payment.name.upper(), transaction.description.upper())
            matched = score >= settings.similarity_threshold
        if not matched:
            continue

        status = _decide_status(payment, amount)
        repository.record_match(
            db,
            recurring_payment_id=payment.id,
            transaction_id=transaction.id,
            cycle_period=cycle_period,
            status=status,
            amount_at_match=amount,
        )
        logger.info(
            "Transaction %s matched to recurring payment %r (cycle %s, status %s)",
            transaction.id, payment.name, cycle_period, status.value,
        )


def _decide_status(payment: RecurringPayment, amount: Decimal) -> RecurringPaymentMatchStatus:
    """WR-18: a never-trusted payment is always pending (FR-6); a trusted payment
    auto-applies only within tolerance, else still falls back to pending (FR-7)."""
    if not payment.is_trusted:
        return RecurringPaymentMatchStatus.PENDING
    if amounts_in_range(
        amount,
        payment.expected_amount,
        ratio_tolerance=settings.recurring_payment_trusted_amount_ratio_tolerance,
        absolute_floor=Decimal(str(settings.recurring_payment_trusted_amount_absolute_floor)),
    ):
        return RecurringPaymentMatchStatus.AUTO_APPLIED
    return RecurringPaymentMatchStatus.PENDING


def is_detection_scan_due_now(db) -> bool:
    latest = repository.find_latest_detection_scan_run(db)
    if latest is None:
        return True
    elapsed = datetime.now(timezone.utc) - latest.ran_at
    return elapsed >= timedelta(hours=settings.recurring_payment_detection_scan_interval_hours)


_TRAILING_REFERENCE_NUMBER = re.compile(r"\s*#?\d{3,}\s*$")


def _normalize_description(description: str) -> str:
    """Strips a trailing reference/invoice-style number (e.g. 'NTUC FAIRPRICE
    #1000' -> 'NTUC FAIRPRICE') so repeat charges from the same merchant group
    together for cadence detection (WR-19), even when each occurrence carries a
    different trailing reference number."""
    return _TRAILING_REFERENCE_NUMBER.sub("", description.strip().upper()).strip()


def _cluster_by_amount(transactions: list[Transaction]) -> list[list[Transaction]]:
    """Greedy clustering: a transaction joins the first existing cluster its amount
    is 'in range' of (WR-19 reuses the same dual-gate helper as WR-18), otherwise it
    starts a new cluster. Handles a normalized description covering more than one
    real-world charge amount (e.g. two unrelated small fees through the same kiosk)."""
    clusters: list[list[Transaction]] = []
    for txn in sorted(transactions, key=_transaction_amount):
        amount = _transaction_amount(txn)
        for existing in clusters:
            if amounts_in_range(
                amount,
                _transaction_amount(existing[0]),
                ratio_tolerance=settings.recurring_payment_trusted_amount_ratio_tolerance,
                absolute_floor=Decimal(str(settings.recurring_payment_trusted_amount_absolute_floor)),
            ):
                existing.append(txn)
                break
        else:
            clusters.append([txn])
    return clusters


def _has_monthly_cadence(cluster: list[Transaction]) -> bool:
    dates = sorted(t.transaction_date for t in cluster)
    if len(dates) < 2:
        return False
    gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
    return any(
        settings.recurring_payment_detection_cadence_min_days <= gap <= settings.recurring_payment_detection_cadence_max_days
        for gap in gaps
    )


def _consistent_category_id(cluster: list[Transaction]) -> UUID | None:
    category_ids = {t.category_id for t in cluster}
    return category_ids.pop() if len(category_ids) == 1 else None


def _merge_groups_via_embedding(groups: dict[str, list[Transaction]]) -> dict[str, list[Transaction]]:
    """WR-22 (Epic 9, corrected from the original Application Design addendum,
    which assumed this scan already called the fuzzy-text matcher -- it doesn't;
    WR-19's own mechanism is exact-normalized-description grouping, a different,
    simpler mechanism find_best_match was never part of). The exact-match grouping
    above stays the primary, always-available mechanism, unchanged -- this pass
    ADDITIONALLY merges two distinct groups when their most-recent transactions'
    embeddings clear the similarity threshold, catching patterns that differ by
    more than a trailing reference number (e.g. paraphrased merchant text) that
    the plain normalized-string match alone would treat as unrelated. Purely
    additive: never splits or weakens the existing grouping.

    Direct pairwise comparison (embedding/similarity.cosine_similarity), not a
    vector-store search -- the candidate pool here is the small number of
    *distinct patterns* found this scan (personal-scale: dozens, not thousands),
    not the full transaction history, so an O(n^2) in-memory comparison is simpler
    and cheap enough, unlike the Categorization Engine's search over potentially
    every historical transaction.
    """
    keys = [k for k in groups if k]  # the empty-string key is skipped downstream anyway (no pattern to merge)
    if len(keys) < 2:
        return groups

    representative: dict[str, Transaction] = {key: max(groups[key], key=lambda t: t.transaction_date) for key in keys}
    representative_vector: dict[str, list[float] | None] = {
        key: embedding_client.compute_embedding(
            embedding_text.build_embedding_text(representative[key].description, _transaction_amount(representative[key]))
        )
        for key in keys
    }  # WR-29: price-bucketed text

    parent = {key: key for key in keys}

    def find(k: str) -> str:
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    def union(a: str, b: str) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_a] = root_b

    def _llm_category(txn: Transaction) -> str | None:
        return txn.llm_suggested_category.name if txn.llm_suggested_category_id else None

    for i, key_a in enumerate(keys):
        vector_a = representative_vector[key_a]
        if vector_a is None:
            continue
        for key_b in keys[i + 1 :]:
            vector_b = representative_vector[key_b]
            if vector_b is None:
                continue
            score = cosine_similarity(vector_a, vector_b)
            # WR-30: symmetric -- either representative's own LLM classification
            # agreeing with the OTHER representative's actual assigned category is
            # enough for the boost.
            txn_a, txn_b = representative[key_a], representative[key_b]
            llm_a, llm_b = _llm_category(txn_a), _llm_category(txn_b)
            if (llm_a and llm_a != UNSURE_NAME and llm_a == txn_b.category.name) or (
                llm_b and llm_b != UNSURE_NAME and llm_b == txn_a.category.name
            ):
                score = min(1.0, score + settings.embedding_llm_agreement_boost)
            if score >= settings.embedding_similarity_threshold:
                union(key_a, key_b)

    merged: dict[str, list[Transaction]] = defaultdict(list)
    for key in keys:
        merged[find(key)].extend(groups[key])
    if "" in groups:
        merged[""] = groups[""]
    return merged


def run_detection_scan(db) -> None:
    """WR-19: monthly-cadence only (FR-12), records new DetectionSuggestion rows,
    skips patterns already covered by an existing match or already suggested
    (BR-22 is the real backstop; this pre-check just avoids a doomed insert)."""
    already_matched_ids = repository.list_matched_transaction_ids(db)
    unmatched = [t for t in repository.list_all_transactions_for_detection(db) if t.id not in already_matched_ids]

    groups: dict[str, list[Transaction]] = defaultdict(list)
    for txn in unmatched:
        groups[_normalize_description(txn.description)].append(txn)

    groups = _merge_groups_via_embedding(groups)  # WR-22 (Epic 9)

    for pattern, txns in groups.items():
        if not pattern:
            continue
        for cluster in _cluster_by_amount(txns):
            if len(cluster) < settings.recurring_payment_detection_min_occurrences:
                continue
            if not _has_monthly_cadence(cluster):
                continue
            if repository.find_suggestion_by_pattern(db, pattern) is not None:
                continue
            most_recent = max(cluster, key=lambda t: t.transaction_date)
            repository.record_detection_suggestion(
                db,
                description_pattern=pattern,
                suggested_amount=_transaction_amount(most_recent),
                suggested_category_id=_consistent_category_id(cluster),
                occurrence_count=len(cluster),
            )
            logger.info("Detected untracked recurring pattern %r (%d occurrences)", pattern, len(cluster))

    repository.record_detection_scan_run(db)
