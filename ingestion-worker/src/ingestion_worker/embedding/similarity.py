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
    # math.sumprod runs in C: the group-merge pass compares every pair of merchant patterns (millions of pairs
    # for a few thousand patterns), which with three Python-level generator sums per pair took tens of minutes.
    dot = math.sumprod(a, b)
    norm_a = math.sqrt(math.sumprod(a, a))
    norm_b = math.sqrt(math.sumprod(b, b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
