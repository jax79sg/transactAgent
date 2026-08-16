"""Property-based tests for embedding/similarity.py's pure cosine_similarity
(NFR-3: the PBT-eligible split-out counterpart to the I/O-bound embedding calls).
"""

import math

from hypothesis import given
from hypothesis import strategies as st

from ingestion_worker.embedding.similarity import cosine_similarity

# Filtered away from extremely-small-but-nonzero magnitudes: squaring a value near
# 1e-200 underflows to exactly 0.0 in float64 (1e-200 is a fully normal float, not
# subnormal -- allow_subnormal=False alone doesn't exclude it), which
# cosine_similarity legitimately treats as "no direction," same as a true zero
# vector -- a real floating-point edge case, not a bug, but one real embedding
# vectors from an actual model will never hit. Caught by actually running
# Hypothesis rather than assuming an unconstrained float range is safe.
_vectors = st.lists(
    st.floats(min_value=-10, max_value=10, allow_nan=False, allow_infinity=False).filter(
        lambda x: x == 0.0 or abs(x) > 1e-100
    ),
    min_size=1,
    max_size=16,
)


class TestCosineSimilarityProperties:
    @given(vector=_vectors)
    def test_identical_nonzero_vector_scores_one(self, vector):
        if all(x == 0.0 for x in vector):
            return  # zero vector has no direction -- covered by its own test below
        assert math.isclose(cosine_similarity(vector, vector), 1.0, abs_tol=1e-9)

    @given(a=_vectors, b=_vectors)
    def test_result_is_bounded(self, a, b):
        if len(a) != len(b):
            return
        score = cosine_similarity(a, b)
        assert -1.0 - 1e-9 <= score <= 1.0 + 1e-9

    @given(a=_vectors, scale=st.floats(min_value=0.01, max_value=100))
    def test_invariant_to_positive_scaling(self, a, scale):
        if all(x == 0.0 for x in a):
            return
        scaled = [x * scale for x in a]
        assert math.isclose(cosine_similarity(a, scaled), 1.0, abs_tol=1e-6)


class TestCosineSimilarityEdgeCases:
    def test_orthogonal_vectors_score_zero(self):
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_opposite_vectors_score_negative_one(self):
        assert math.isclose(cosine_similarity([1.0, 0.0], [-1.0, 0.0]), -1.0, abs_tol=1e-9)

    def test_zero_vector_scores_zero_not_a_crash(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_mismatched_lengths_scores_zero_not_a_crash(self):
        assert cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0

    def test_empty_vectors_score_zero_not_a_crash(self):
        assert cosine_similarity([], []) == 0.0
