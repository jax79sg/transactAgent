"""Price-range bucket text (WR-29, Matching Precision Refinement) -- appended to a
transaction description / RecurringPayment name before embedding, both at query
time (Categorization Engine, Recurring Payment Manager) and storage time
(Embedding Manager's processNextEmbeddingBatch). WR-24's "raw, unmodified text"
principle still holds for the description/name portion itself.

WR-36/WR-37/WR-40/WR-41 (Recategorization Algorithm Rework) add transformations
before embedding: a direction token (WR-36), stripping known boilerplate
reference-code noise (WR-37, skipped for PayNow-Mobile transfers per WR-41),
and stripping known generic trailing boilerplate phrases (WR-40) -- see
build_embedding_text.
"""

import re
from decimal import Decimal

from ingestion_worker.config import settings

# WR-37: delimiter-anchored, not a blanket "strip any alphanumeric token" rule --
# deliberately conservative so a genuine payee/merchant name containing digits is
# never touched. Case-insensitive; whichever delimiter occurs first wins, and
# everything from it onward is dropped.
_REFERENCE_NOISE_PATTERN = re.compile(r"(OTHR\s*-\s*|REF:).*$", re.IGNORECASE)

# WR-41: PayNow-Mobile transfers are person-to-person -- found live that the
# OTHR-/REF: suffix there is often a real free-text note the user relied on to
# categorize it (e.g. "OTHR-gold bar" vs. "OTHR-shanghai trip" vs. "OTHR-hongbaos",
# categorized Others/Vacation/Gift respectively), unlike PayNow-UEN (business)
# transfers where the suffix is a random reference code. WR-37's stripping is
# skipped whenever this marker is present, so that signal survives into the
# embedding instead of being discarded as if it were noise.
_PAYNOW_MOBILE_MARKER = re.compile(r"paynow-mobile", re.IGNORECASE)

# WR-40: generic boilerplate phrases that dominate embedding similarity across
# genuinely unrelated merchants (found live: "MISTER MINIT ARC Card Payment" vs.
# "AMAZON MKTPLC Card Payment" scored higher against each other than either did
# against ITS OWN real precedent, purely from sharing this suffix). Stripped
# wherever the phrase occurs, case-insensitive, not just as a trailing suffix --
# unlike _REFERENCE_NOISE_PATTERN this removes only the phrase itself, not
# everything after it, since these aren't delimiters marking noise that follows.
_BOILERPLATE_PHRASE_PATTERN = re.compile(r"\bcard payment\b", re.IGNORECASE)


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


def _strip_reference_noise(description: str) -> str:
    """WR-37: strips text from the first "OTHR-"/"OTHR - "/"REF:" onward (case-
    insensitive) -- the exact boilerplate patterns found carrying reference-code
    noise in live evidence (e.g. "...OTHR-DICNP17537901512105MMHTZ8"). WR-41: this
    stripping is skipped for PayNow-Mobile transfers, where the suffix is often a
    genuine free-text note rather than noise. WR-40: also strips the generic "Card
    Payment" boilerplate phrase wherever it occurs, regardless of transfer type.
    Only affects what gets embedded; the caller's own `description` string is
    never mutated."""
    if _PAYNOW_MOBILE_MARKER.search(description):
        without_reference_noise = description
    else:
        without_reference_noise = _REFERENCE_NOISE_PATTERN.sub("", description)
    without_boilerplate_phrases = _BOILERPLATE_PHRASE_PATTERN.sub("", without_reference_noise)
    return without_boilerplate_phrases.strip()


def build_embedding_text(description: str, amount: Decimal, direction: str) -> str:
    """`direction` is `"inflow"` or `"outflow"` (WR-36) -- callers derive it from
    whichever of a Transaction's out_flow/in_flow is set (BR-2: exactly one always
    is); see categorization/service.py's and recurring_payments/service.py's
    `_transaction_direction` helpers."""
    cleaned = _strip_reference_noise(description)
    return f"{cleaned} | {price_bucket_label(amount)} | {direction}"
