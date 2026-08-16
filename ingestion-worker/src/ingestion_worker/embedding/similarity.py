"""Pure embedding-vector math (NFR-3: out-of-scope-for-PBT I/O is confined to
client.py/vector_store.py; this module is the PBT-eligible split-out counterpart,
mirroring categorization/similarity.py's "deliberately pure" framing).
"""

import math


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Standard cosine similarity, 0.0-1.0 for the non-negative embedding spaces
    this project deals with (can go negative for arbitrary vectors, but every
    caller only ever compares this against `embedding_similarity_threshold`, which
    is itself in the same range the embedding model actually produces).

    Used directly (not via Qdrant) by callers comparing exactly two known vectors
    in-memory -- the retroactive recategorization re-scan's pairwise check, and
    runDetectionScan's group-merge pass (WR-22) -- as opposed to a genuine
    nearest-neighbor search over a large candidate pool, which goes through
    `vector_store.query_nearest_neighbors` instead.
    """
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
