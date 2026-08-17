"""Tests for embedding/text.py's pure price_bucket_label/build_embedding_text
(WR-29, Matching Precision Refinement -- NFR-MPR-5/NFR-3-style PBT eligibility,
same convention as test_embedding_similarity.py for this unit's other pure
embedding-adjacent function).
"""

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from ingestion_worker.embedding.text import build_embedding_text, price_bucket_label

# Default boundaries (config.py): 1,5,10,20,50,100,200,500,1000,2000,5000
_amounts = st.decimals(min_value="0", max_value="100000", places=2, allow_nan=False, allow_infinity=False)


class TestPriceBucketLabelProperties:
    @given(amount=_amounts)
    def test_always_returns_a_dollar_prefixed_label(self, amount):
        label = price_bucket_label(amount)
        assert label.startswith("$")

    @given(amount=_amounts)
    def test_negative_and_positive_of_same_magnitude_bucket_identically(self, amount):
        assert price_bucket_label(amount) == price_bucket_label(-amount)


class TestPriceBucketLabelEdgeCases:
    def test_zero_falls_in_first_bucket(self):
        assert price_bucket_label(Decimal(0)) == "$0 to $1"

    def test_amount_exactly_on_a_boundary_falls_in_the_lower_bucket(self):
        assert price_bucket_label(Decimal(5)) == "$1 to $5"

    def test_amount_just_above_a_boundary_falls_in_the_next_bucket(self):
        assert price_bucket_label(Decimal("5.01")) == "$5 to $10"

    def test_amount_above_last_boundary_is_open_ended(self):
        assert price_bucket_label(Decimal(6000)) == "$5000+"

    def test_negative_amount_buckets_by_magnitude(self):
        """out_flow/in_flow are both stored positive (BR-2), but this function is
        sign-agnostic regardless -- matching amounts_in_range's own magnitude-only
        reasoning."""
        assert price_bucket_label(Decimal(-3)) == price_bucket_label(Decimal(3))


class TestBuildEmbeddingText:
    def test_appends_bucket_label_to_description(self):
        text = build_embedding_text("NTUC FAIRPRICE", Decimal("3.50"))
        assert text == "NTUC FAIRPRICE | $1 to $5"

    def test_preserves_description_prefix(self):
        text = build_embedding_text("STARBUCKS #4521", Decimal(6000))
        assert text.startswith("STARBUCKS #4521 | ")
