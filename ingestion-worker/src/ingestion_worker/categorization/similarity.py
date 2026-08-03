"""Pure similarity-matching function (Functional Design Question 3 = A, WR-3).

Deliberately pure (no DB/I/O) so it's a clean target for property-based testing
(Hypothesis, Partial PBT mode per requirements.md NFR-5.2).
"""

from dataclasses import dataclass

from rapidfuzz import fuzz

MANUAL_SOURCE = "manual"


@dataclass(frozen=True)
class SimilarityCandidate:
    transaction_id: str
    description: str
    category_name: str
    category_source: str  # "manual" | "similarity" | "llm"


@dataclass(frozen=True)
class SimilarityMatch:
    candidate: SimilarityCandidate
    score: float


def find_best_match(
    description: str, candidates: list[SimilarityCandidate], threshold: float
) -> SimilarityMatch | None:
    """WR-3: only matches clearing `threshold` are eligible. Among those, a
    `manual`-sourced candidate is preferred over any non-manual candidate regardless
    of relative fuzzy score; ties within the same source-tier are broken by score,
    then by candidate order (stable, deterministic)."""
    scored = [
        SimilarityMatch(candidate=c, score=fuzz.token_sort_ratio(description, c.description))
        for c in candidates
    ]
    eligible = [m for m in scored if m.score >= threshold]
    if not eligible:
        return None

    manual_matches = [m for m in eligible if m.candidate.category_source == MANUAL_SOURCE]
    pool = manual_matches if manual_matches else eligible
    return max(pool, key=lambda m: m.score)
