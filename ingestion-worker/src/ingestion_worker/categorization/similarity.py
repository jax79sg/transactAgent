"""Pure similarity-matching function (Functional Design Question 3 = A, WR-3).

Deliberately pure (no DB/I/O) so it's a clean target for property-based testing
(Hypothesis, Partial PBT mode per requirements.md NFR-5.2).
"""

from dataclasses import dataclass
from decimal import Decimal

from rapidfuzz import fuzz

MANUAL_SOURCE = "manual"


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


def _amounts_in_range(a: Decimal, b: Decimal, *, ratio_tolerance: float, absolute_floor: Decimal) -> bool:
    """Two amounts are "in range" of each other if either is true:
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
    amount range of `amount` (see `_amounts_in_range`) are eligible. Among those, a
    `manual`-sourced candidate is preferred over any non-manual candidate regardless
    of relative fuzzy score; ties within the same source-tier are broken by score,
    then by candidate order (stable, deterministic)."""
    scored = [
        SimilarityMatch(candidate=c, score=fuzz.token_sort_ratio(description, c.description))
        for c in candidates
        if _amounts_in_range(
            amount, c.amount, ratio_tolerance=amount_ratio_tolerance, absolute_floor=amount_absolute_floor
        )
    ]
    eligible = [m for m in scored if m.score >= threshold]
    if not eligible:
        return None

    manual_matches = [m for m in eligible if m.candidate.category_source == MANUAL_SOURCE]
    pool = manual_matches if manual_matches else eligible
    return max(pool, key=lambda m: m.score)
