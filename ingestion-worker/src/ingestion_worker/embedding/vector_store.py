"""VectorStoreClient (business-logic-model.md — Vector Store Client Component).

All interaction with Qdrant, the two logical collections `transactions` and
`recurring_payment_names` (WR-22). Same no-retry/immediate-soft-fail philosophy as
embedding/client.py (nfr-design-patterns.md) -- every function swallows its own
errors and reports unavailability via its return value, never raises out to a
caller. `ensure_collections()` additionally implements NFR Design's "Non-Blocking
Vector Store Startup" pattern: even though Qdrant is this project's own
docker-compose service (not a user-managed external dependency like oMLX), FR-10's
soft-dependency framing covers the whole embedding subsystem, so a Qdrant outage at
startup must not block the worker's unrelated responsibilities.
"""

import logging

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from ingestion_worker.config import settings

logger = logging.getLogger(__name__)

TRANSACTIONS_COLLECTION = "transactions"
RECURRING_PAYMENT_NAMES_COLLECTION = "recurring_payment_names"
_COLLECTIONS = (TRANSACTIONS_COLLECTION, RECURRING_PAYMENT_NAMES_COLLECTION)

_REQUEST_TIMEOUT_SECONDS = 5


def _client() -> QdrantClient:
    return QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port, timeout=_REQUEST_TIMEOUT_SECONDS)


def ensure_collections() -> None:
    """Called once at worker startup (main.py). Best-effort, never raises -- a
    failure here just means every embedding call site falls back to fuzzy-text
    until Qdrant becomes reachable (WR-25's soft-fail extends to this project's own
    vector-db container, not just the user-managed oMLX endpoint)."""
    try:
        client = _client()
        existing = {c.name for c in client.get_collections().collections}
        for name in _COLLECTIONS:
            if name not in existing:
                client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(size=settings.embedding_dimensions, distance=Distance.COSINE),
                )
                logger.info("Created vector store collection %r", name)
    except Exception:  # noqa: BLE001 - non-blocking startup pattern (nfr-design-patterns.md)
        logger.warning(
            "Vector store collection setup failed (Qdrant unreachable?) -- embedding "
            "features will degrade gracefully to fuzzy-text matching until it recovers",
            exc_info=True,
        )


def upsert_embedding(collection: str, entity_id: str, vector: list[float]) -> bool:
    """WR-26: idempotent -- the same entity_id always overwrites its own prior
    vector, so a crash-and-retry never duplicates or corrupts state. Returns False
    (never raises) on any failure -- callers stop early / soft-fail per WR-25."""
    try:
        _client().upsert(collection_name=collection, points=[PointStruct(id=entity_id, vector=vector)])
        return True
    except Exception:  # noqa: BLE001 - WR-25
        logger.info("Vector store upsert unavailable (collection=%r)", collection, exc_info=True)
        return False


def query_nearest_neighbors(
    vector: list[float], collection: str, *, top_k: int, exclude_entity_id: str | None = None
) -> list[tuple[str, float]] | None:
    """WR-21/22/23. Returns a list of (entity_id, similarity_score) pairs, nearest
    first, or `None` if the query itself could not be performed (Qdrant
    unreachable/erroring) -- distinct from a successful query finding zero results
    (`[]`). Callers treat both `None` and `[]` as "no embedding candidate" (WR-21
    step 4), but keeping them distinct aids debugging/logging.

    `exclude_entity_id` (WR-21: the retroactive re-scan's source transaction; each
    representative during runDetectionScan's group-merge pass) is applied by
    over-fetching by one and filtering in Python -- simpler than a Qdrant payload
    filter for this project's personal-scale data volume, and avoids needing to
    store `id` redundantly as payload just to filter on it.
    """
    try:
        limit = top_k + 1 if exclude_entity_id is not None else top_k
        response = _client().query_points(collection_name=collection, query=vector, limit=limit)
    except Exception:  # noqa: BLE001 - WR-25
        logger.info("Vector store query unavailable (collection=%r)", collection, exc_info=True)
        return None
    results = [(str(point.id), point.score) for point in response.points if str(point.id) != exclude_entity_id]
    return results[:top_k]
