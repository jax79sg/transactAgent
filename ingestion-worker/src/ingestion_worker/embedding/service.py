"""Embedding Manager Component (business-logic-model.md). Owns *when* embeddings
get computed and persisted -- the poll-cycle batch job (WR-26), checked as
`poll_once()`'s fifth, lowest-priority branch (main.py / services.md correction).

Query-time embedding computation (the transient, non-persisted kind used by the
Categorization Engine and Recurring Payment Manager at match time, WR-21) is NOT
here -- it's a direct call to `embedding.client.compute_embedding` from each of
those modules, since it's just one step of an algorithm those modules already own
(business-logic-model.md's addenda live inside the Categorization Engine /
Recurring Payment Manager sections, not this one).
"""

import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from ingestion_worker.config import settings
from ingestion_worker.embedding import client, repository, vector_store
from ingestion_worker.embedding import text as embedding_text

logger = logging.getLogger(__name__)


def _compute_embeddings_concurrently(texts: list[str]) -> list[list[float] | None]:
    """WR-40 (Recategorization Algorithm Rework): the HTTP round-trip to the local
    embedding endpoint is the bottleneck, not anything CPU-bound in this process --
    computed concurrently, bounded by embedding_concurrency (same reasoning/same
    default as llm_classification_concurrency, same local model server, same
    overload concern). Order-preserving: index i of the result corresponds to
    index i of `texts`, regardless of completion order."""
    with ThreadPoolExecutor(max_workers=settings.embedding_concurrency) as executor:
        return list(executor.map(client.compute_embedding, texts))


def process_next_embedding_batch(db: Session) -> int:
    """WR-26: a bounded batch of pending Transaction rows, then a bounded batch of
    pending RecurringPayment rows. WR-40: each batch's embeddings are computed
    concurrently (the HTTP calls), but written to the DB/vector store in the same
    deterministic ascending order the rows were fetched in -- stops early the
    moment either the embedding endpoint or the vector store proves unavailable,
    rather than burning through the rest of the batch on doomed calls (FR-10).
    Concurrently-computed vectors for rows past the failure point are simply
    discarded (those rows stay `pending`, retried next cycle) -- no data loss,
    just wasted work for this one cycle.
    """
    processed = 0

    transactions = repository.list_pending_transactions(db, limit=settings.embedding_batch_size)
    if transactions:
        texts = [
            embedding_text.build_embedding_text(  # WR-29/WR-36
                txn.description,
                txn.out_flow if txn.out_flow is not None else txn.in_flow,
                "outflow" if txn.out_flow is not None else "inflow",
            )
            for txn in transactions
        ]
        vectors = _compute_embeddings_concurrently(texts)
        for txn, vector in zip(transactions, vectors, strict=True):
            if vector is None:
                return processed
            if not vector_store.upsert_embedding(
                collection=vector_store.TRANSACTIONS_COLLECTION, entity_id=str(txn.id), vector=vector
            ):
                return processed
            repository.mark_transaction_embedded(db, txn)
            processed += 1

    payments = repository.list_pending_recurring_payments(db, limit=settings.embedding_batch_size)
    if payments:
        # WR-29: same price-bucketed text convention as transactions above. WR-36:
        # RecurringPayment has no direction field of its own -- always "outflow"
        # (this domain's recurring payments are overwhelmingly outgoing), matching
        # recurring_payments/service.py's _embedding_candidate_scores query side.
        texts = [
            embedding_text.build_embedding_text(payment.name, payment.expected_amount, "outflow") for payment in payments
        ]
        vectors = _compute_embeddings_concurrently(texts)
        for payment, vector in zip(payments, vectors, strict=True):
            if vector is None:
                return processed
            if not vector_store.upsert_embedding(
                collection=vector_store.RECURRING_PAYMENT_NAMES_COLLECTION, entity_id=str(payment.id), vector=vector
            ):
                return processed
            repository.mark_recurring_payment_embedded(db, payment)
            processed += 1

    if processed:
        logger.info("Embedding batch: processed %d row(s)", processed)
    return processed
