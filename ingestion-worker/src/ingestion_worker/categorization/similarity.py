"""Pure similarity-matching function (Functional Design Question 3 = A, WR-3).

Deliberately pure (no DB/I/O) so it's a clean target for property-based testing
(Hypothesis, Partial PBT mode per requirements.md NFR-5.2).
"""

import re
from dataclasses import dataclass
from decimal import Decimal

from rapidfuzz import fuzz

MANUAL_SOURCE = "manual"

_DIGIT_RUN = re.compile(r"\b\d{3,}\b")
_SHORT_MIXED_ALPHANUMERIC = re.compile(
    r"\b(?=[A-Za-z0-9]{1,12}\b)(?=[A-Za-z0-9]*[A-Za-z])(?=[A-Za-z0-9]*\d)[A-Za-z0-9]+\b"
)
_WHITESPACE_RUN = re.compile(r"\s+")


def normalize_reference_noise(description: str) -> str:
    """WR-20: strips reference-code-shaped noise before fuzzy scoring, so a repeat
    payment to the same payee isn't blocked from matching purely by a unique
    per-transaction reference code embedded in the description text (e.g. PayNow's
    `OTHR-260102595543212111` or `OTHR-QR3 dy01qkET 00747`).

    Bank/rail-agnostic (not hardcoded to "PayNow") but conservative: only strips
    whole tokens shaped like a reference code -- (1) runs of 3+ consecutive digits,
    or (2) short (<=12 char) tokens mixing letters and digits -- leaving payee/
    merchant text untouched. Known, accepted limitation: a genuine short letter+digit
    merchant name (e.g. a hypothetical "3M") would also be stripped -- an explicit
    trade-off of this heuristic, not a defect. See aidlc-docs/audit.md 2026-08-11.

    Standalone and scoped to this module's matching path only -- not shared with
    `recurring_payments/service.py`'s unrelated `_normalize_description`, which
    serves exact-match cadence clustering, a different purpose.
    """
    normalized = _DIGIT_RUN.sub(" ", description)
    normalized = _SHORT_MIXED_ALPHANUMERIC.sub(" ", normalized)
    return _WHITESPACE_RUN.sub(" ", normalized).strip()


@dataclass(frozen=True)
class SimilarityCandidate:
    transaction_id: str
    description: str
    category_name: str
    category_source: str  # "manual" | "similarity" | "llm"
    amount: Decimal


@dataclass(frozen=True)
class SimilarityMatch:
    candidate: SimilarityCandidate
    score: float


def amounts_in_range(a: Decimal, b: Decimal, *, ratio_tolerance: float, absolute_floor: Decimal) -> bool:
    """Public (not module-private) since Epic 8's Recurring Payment Manager also
    calls this directly for its trust/tolerance auto-apply check (WR-18) -- unlike
    `find_best_match` below, recurring-payment candidate selection (WR-16) does NOT
    gate on amount at all (expected_amount is a loose guide, never a hard filter),
    so only this narrower helper is reused there, not the whole function.

    Two amounts are "in range" of each other if either is true:
    - they're within `absolute_floor` of each other (handles small-value line items
      -- e.g. two currency-conversion fees of $0.01 and $0.27 -- where the ratio
      alone would be huge but the values are trivially close in real terms), or
    - the larger is at most `ratio_tolerance` times the smaller (handles genuine
      month-to-month drift on a recurring bill, e.g. a fuel top-up or a premium that
      varies a bit, without accepting wildly different amounts as "the same kind of
      transaction" just because the merchant text matches).

    Real incident this exists for: two OCBC "FAST PAYMENT via PayNow-UEN to AXS
    PTE. LTD." transactions -- AXS is a bill-payment kiosk used for many unrelated
    bill types -- with near-identical description text but wildly different
    amounts ($699 a car loan installment, $81.70 a conservancy fee). Correcting one
    surfaced the other as a suggested match purely on text similarity. See
    aidlc-docs/audit.md 2026-08-06.
    """
    low, high = (a, b) if a <= b else (b, a)
    if high - low <= absolute_floor:
        return True
    if low <= 0:
        return False
    return high / low <= Decimal(str(ratio_tolerance))


def select_best_match(scored: list[SimilarityMatch]) -> SimilarityMatch | None:
    """WR-3's selection rule, factored out so both the fuzzy-text path
    (`find_best_match` below) and the embedding-based path (Epic 9,
    `categorization/service.py`'s `find_similar_transaction_via_embedding`, WR-23)
    apply it identically: among already-eligible candidates (threshold AND
    amount-range already passed), a `manual`-sourced candidate is preferred over
    any non-manual candidate regardless of relative score; ties within the same
    source-tier are broken by score, then by candidate order (stable,
    deterministic)."""
    if not scored:
        return None
    manual_matches = [m for m in scored if m.candidate.category_source == MANUAL_SOURCE]
    pool = manual_matches or scored
    return max(pool, key=lambda m: m.score)


def find_best_match(
    description: str,
    amount: Decimal,
    candidates: list[SimilarityCandidate],
    threshold: float,
    *,
    amount_ratio_tolerance: float,
    amount_absolute_floor: Decimal,
) -> SimilarityMatch | None:
    """WR-3: only matches clearing `threshold` on description text AND within
    amount range of `amount` (see `amounts_in_range`) are eligible. Selection among
    eligible matches is `select_best_match`'s job."""
    normalized_description = normalize_reference_noise(description)
    scored = [
        SimilarityMatch(
            candidate=c,
            score=fuzz.token_sort_ratio(normalized_description, normalize_reference_noise(c.description)),
        )
        for c in candidates
        if amounts_in_range(
            amount, c.amount, ratio_tolerance=amount_ratio_tolerance, absolute_floor=amount_absolute_floor
        )
    ]
    eligible = [m for m in scored if m.score >= threshold]
    return select_best_match(eligible)
