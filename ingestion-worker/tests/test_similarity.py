"""Property-based tests for the pure similarity-matching function (WR-3).

Partial PBT mode (requirements.md NFR-5.2): this is exactly the kind of pure,
no-I/O function PBT is meant for.
"""

from hypothesis import given
from hypothesis import strategies as st

from ingestion_worker.categorization.similarity import SimilarityCandidate, find_best_match

_descriptions = st.text(min_size=1, max_size=100, alphabet=st.characters(blacklist_categories=("Cs",)))
_sources = st.sampled_from(["manual", "similarity", "llm"])


def _candidate_strategy():
    return st.builds(
        SimilarityCandidate,
        transaction_id=st.uuids().map(str),
        description=_descriptions,
        category_name=st.text(min_size=1, max_size=30),
        category_source=_sources,
    )


class TestFindBestMatchProperties:
    @given(description=_descriptions, candidates=st.lists(_candidate_strategy(), max_size=20), threshold=st.floats(min_value=0, max_value=100))
    def test_result_is_none_or_a_candidate_from_the_input_list(self, description, candidates, threshold):
        result = find_best_match(description, candidates, threshold)
        if result is not None:
            assert result.candidate in candidates
            assert 0 <= result.score <= 100

    @given(description=_descriptions, candidates=st.lists(_candidate_strategy(), max_size=20))
    def test_higher_threshold_never_yields_more_permissive_result(self, description, candidates):
        """Property: raising the threshold can only ever exclude matches, never include more."""
        loose = find_best_match(description, candidates, threshold=0)
        strict = find_best_match(description, candidates, threshold=100)
        if strict is not None:
            assert loose is not None
            assert strict.score >= loose.score or strict.score == 100

    @given(description=_descriptions)
    def test_empty_candidate_list_never_matches(self, description):
        assert find_best_match(description, [], threshold=0) is None

    @given(description=_descriptions, candidates=st.lists(_candidate_strategy(), min_size=1, max_size=20))
    def test_all_scores_below_threshold_yields_none(self, description, candidates):
        # threshold=101 is unreachable (scores are 0-100), so nothing can ever qualify
        assert find_best_match(description, candidates, threshold=101) is None

    def test_exact_match_scores_100(self):
        candidate = SimilarityCandidate(
            transaction_id="t1", description="NTUC FAIRPRICE", category_name="Groceries", category_source="llm"
        )
        result = find_best_match("NTUC FAIRPRICE", [candidate], threshold=50)
        assert result is not None
        assert result.score == 100

    def test_manual_precedence_over_higher_scoring_non_manual(self):
        """WR-3: a manual match wins even if a non-manual candidate scores higher."""
        manual = SimilarityCandidate(
            transaction_id="m1", description="STARBUCKS COFFEE SG", category_name="Dining", category_source="manual"
        )
        higher_scoring_llm = SimilarityCandidate(
            transaction_id="l1", description="STARBUCKS", category_name="Entertainment", category_source="llm"
        )
        result = find_best_match("STARBUCKS COFFEE", [manual, higher_scoring_llm], threshold=50)
        assert result is not None
        assert result.candidate.category_source == "manual"
        assert result.candidate.category_name == "Dining"

    def test_no_manual_candidate_falls_back_to_highest_scoring(self):
        similarity_match = SimilarityCandidate(
            transaction_id="s1", description="GRAB RIDE", category_name="Transport", category_source="similarity"
        )
        llm_match = SimilarityCandidate(
            transaction_id="l1", description="GRAB", category_name="Others", category_source="llm"
        )
        result = find_best_match("GRAB RIDE HOME", [similarity_match, llm_match], threshold=30)
        assert result is not None
        assert result.candidate.transaction_id == "s1"  # closer textual match, no manual present
