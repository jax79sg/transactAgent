"""Price-range bucket text (WR-29, Matching Precision Refinement) -- appended to a
transaction description / RecurringPayment name before embedding, both at query
time (Categorization Engine, Recurring Payment Manager) and storage time
(Embedding Manager's processNextEmbeddingBatch). WR-24's "raw, unmodified text"
principle still holds for the description/name portion itself -- only this suffix
is new.
"""

from decimal import Decimal

from ingestion_worker.config import settings


def _boundaries() -> tuple[Decimal, ...]:
    return tuple(Decimal(b.strip()) for b in settings.embedding_price_bucket_boundaries.split(",") if b.strip())


def price_bucket_label(amount: Decimal) -> str:
    """Ascending, open-ended top bucket -- e.g. "$0 to $1", "$1 to $5", ...,
    "$5000+" for anything above the last configured boundary. Sign-agnostic
    (buckets on magnitude, matching amounts_in_range's own magnitude-only
    reasoning -- out_flow/in_flow are both stored positive, BR-2)."""
    magnitude = abs(amount)
    lower = Decimal(0)
    for boundary in _boundaries():
        if magnitude <= boundary:
            return f"${lower} to ${boundary}"
        lower = boundary
    return f"${lower}+"


def build_embedding_text(description: str, amount: Decimal) -> str:
    return f"{description} | {price_bucket_label(amount)}"
