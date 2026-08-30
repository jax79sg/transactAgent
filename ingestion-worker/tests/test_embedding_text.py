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
    def test_appends_bucket_label_and_direction_to_description(self):
        text = build_embedding_text("NTUC FAIRPRICE", Decimal("3.50"), "outflow")
        assert text == "NTUC FAIRPRICE | $1 to $5 | outflow"

    def test_preserves_description_prefix(self):
        text = build_embedding_text("STARBUCKS #4521", Decimal(6000), "outflow")
        assert text.startswith("STARBUCKS #4521 | ")

    def test_inflow_direction_appended(self):
        text = build_embedding_text("SALARY CREDIT", Decimal(3000), "inflow")
        assert text.endswith("| inflow")


class TestReferenceCodeStripping:
    """WR-37: delimiter-anchored stripping -- only text after a known boilerplate
    delimiter is dropped, never a blanket "any long alphanumeric token" rule."""

    def test_strips_after_othr_dash(self):
        text = build_embedding_text(
            "FAST PAYMENT via PayNow-UEN to HITPAY PAYMENTS OTHR-DICNP17537901512105MMHTZ8", Decimal(50), "outflow"
        )
        assert "DICNP17537901512105MMHTZ8" not in text
        assert "HITPAY PAYMENTS" in text

    def test_strips_after_othr_dash_with_spaces(self):
        text = build_embedding_text(
            "FAST PAYMENT via PayNow-UEN to NOVALAND PTE. LT OTHR - EPOSSPSPTWM8J GOJ IIFTRGNB", Decimal(50), "outflow"
        )
        assert "EPOSSPSPTWM8J" not in text
        assert "NOVALAND PTE. LT" in text

    def test_strips_after_ref_colon(self):
        text = build_embedding_text("PAYMENT REF:INV20260828001", Decimal(50), "outflow")
        assert "INV20260828001" not in text

    def test_case_insensitive_delimiter_match(self):
        text = build_embedding_text("PAYMENT othr-abc123", Decimal(50), "outflow")
        assert "abc123" not in text

    def test_no_delimiter_present_leaves_description_untouched(self):
        """A genuine payee name containing digits, with no boilerplate delimiter
        anywhere in the string, must never be stripped."""
        text = build_embedding_text("Qashier-DELIGHT99 Cafe", Decimal(10), "outflow")
        assert "Qashier-DELIGHT99 Cafe" in text


class TestBoilerplatePhraseStripping:
    """WR-40: generic trailing boilerplate phrases (found live: "Card Payment"
    dominating similarity across unrelated merchants) are stripped wherever they
    occur, not just as a suffix -- unlike the delimiter-anchored WR-37 patterns,
    the phrase itself is the noise, not a marker for what follows it."""

    def test_strips_card_payment_suffix(self):
        text = build_embedding_text("MISTER MINIT ARC Card Payment", Decimal(50), "outflow")
        assert "Card Payment" not in text
        assert "MISTER MINIT ARC" in text

    def test_case_insensitive(self):
        text = build_embedding_text("AMAZON MKTPLC card payment", Decimal(50), "outflow")
        assert "card payment" not in text.lower()
        assert "AMAZON MKTPLC" in text

    def test_does_not_strip_partial_word_match(self):
        """Word-boundary anchored -- must not corrupt a merchant name that merely
        contains "card" or "payment" as a substring of a longer word."""
        text = build_embedding_text("DISCARDED ITEMS PAYMENTOR PTE LTD", Decimal(50), "outflow")
        assert "DISCARDED ITEMS PAYMENTOR PTE LTD" in text

    def test_combines_with_reference_noise_stripping(self):
        """Both WR-37 and WR-40 stripping apply together, not one-or-the-other."""
        text = build_embedding_text(
            "SOME MERCHANT Card Payment OTHR-REF123456789", Decimal(50), "outflow"
        )
        assert "Card Payment" not in text
        assert "REF123456789" not in text


class TestPayNowMobileExemption:
    """WR-41: PayNow-Mobile (person-to-person) transfers keep their OTHR-/REF:
    suffix -- it's often a genuine free-text note the user relies on to
    categorize the transfer, unlike PayNow-UEN (business) transfers where the
    same-shaped suffix is a random reference code and should still be stripped."""

    def test_paynow_mobile_suffix_is_preserved(self):
        text = build_embedding_text(
            "FAST PAYMENT via PayNow-Mobile to Verena OTHR-gold bar", Decimal(1400), "outflow"
        )
        assert "gold bar" in text

    def test_paynow_uen_suffix_is_still_stripped(self):
        """The exemption is specific to PayNow-Mobile -- PayNow-UEN keeps WR-37's
        original stripping behavior unchanged."""
        text = build_embedding_text(
            "FAST PAYMENT via PayNow-UEN to HITPAY PAYMENTS OTHR - DICNP17537901512105MMHTZ8",
            Decimal(50), "outflow",
        )
        assert "DICNP17537901512105MMHTZ8" not in text

    def test_paynow_mobile_case_insensitive(self):
        text = build_embedding_text(
            "fast payment via paynow-mobile to Sam OTHR-lunch money", Decimal(20), "outflow"
        )
        assert "lunch money" in text

    def test_card_payment_phrase_still_stripped_for_paynow_mobile(self):
        """WR-40's phrase stripping is unconditional -- only WR-37's delimiter
        stripping is exempted for PayNow-Mobile."""
        text = build_embedding_text(
            "FAST PAYMENT via PayNow-Mobile to Sam Card Payment OTHR-lunch money", Decimal(20), "outflow"
        )
        assert "Card Payment" not in text
        assert "lunch money" in text
