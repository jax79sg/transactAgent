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

from sqlalchemy.orm import Session

from ingestion_worker.config import settings
from ingestion_worker.embedding import client, repository, vector_store
from ingestion_worker.embedding import text as embedding_text

logger = logging.getLogger(__name__)


def process_next_embedding_batch(db: Session) -> int:
    """WR-26: a bounded batch of pending Transaction rows, then a bounded batch of
    pending RecurringPayment rows, each processed in deterministic order. Stops
    early (returns immediately) the moment either the embedding endpoint or the
    vector store proves unavailable, rather than burning through the rest of the
    batch on doomed calls (FR-10) -- already-processed rows earlier in the same
    call are unaffected, since the status flip happens per-row, immediately after
    that row's own upsert succeeds.
    """
    processed = 0

    for txn in repository.list_pending_transactions(db, limit=settings.embedding_batch_size):
        amount = txn.out_flow if txn.out_flow is not None else txn.in_flow
        vector = client.compute_embedding(embedding_text.build_embedding_text(txn.description, amount))  # WR-29
        if vector is None:
            return processed
        if not vector_store.upsert_embedding(
            collection=vector_store.TRANSACTIONS_COLLECTION, entity_id=str(txn.id), vector=vector
        ):
            return processed
        repository.mark_transaction_embedded(db, txn)
        processed += 1

    for payment in repository.list_pending_recurring_payments(db, limit=settings.embedding_batch_size):
        # WR-29: same price-bucketed text convention as transactions above.
        vector = client.compute_embedding(embedding_text.build_embedding_text(payment.name, payment.expected_amount))
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
