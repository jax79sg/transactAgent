"""Property-based tests for the pure similarity-matching function (WR-3).

Partial PBT mode (requirements.md NFR-5.2): this is exactly the kind of pure,
no-I/O function PBT is meant for.
"""

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from ingestion_worker.categorization.similarity import (
    SimilarityCandidate,
    find_best_match,
    normalize_reference_noise,
)

_descriptions = st.text(min_size=1, max_size=100, alphabet=st.characters(blacklist_categories=("Cs",)))
_sources = st.sampled_from(["manual", "similarity", "llm"])

# A fixed amount shared by the description-side and every candidate in the
# text-matching property tests below: trivially "in range" of itself under any
# tolerance, so these tests continue to exercise only the text-matching behavior
# they're named for, unaffected by the amount gate (which has its own dedicated
# test class further down). Real, non-trivial ratio_tolerance/absolute_floor
# values are used regardless (not e.g. math.inf) so a bug that broke the gate
# entirely wouldn't be masked by a permissive test setup.
_FIXED_AMOUNT = Decimal("10.00")
_RATIO_TOLERANCE = 4.0
_ABSOLUTE_FLOOR = Decimal("5.00")


def _candidate_strategy():
    return st.builds(
        SimilarityCandidate,
        transaction_id=st.uuids().map(str),
        description=_descriptions,
        category_name=st.text(min_size=1, max_size=30),
        category_source=_sources,
        amount=st.just(_FIXED_AMOUNT),
    )


def _find_best_match(description, candidates, threshold):
    return find_best_match(
        description,
        _FIXED_AMOUNT,
        candidates,
        threshold,
        amount_ratio_tolerance=_RATIO_TOLERANCE,
        amount_absolute_floor=_ABSOLUTE_FLOOR,
    )


class TestFindBestMatchProperties:
    @given(description=_descriptions, candidates=st.lists(_candidate_strategy(), max_size=20), threshold=st.floats(min_value=0, max_value=100))
    def test_result_is_none_or_a_candidate_from_the_input_list(self, description, candidates, threshold):
        result = _find_best_match(description, candidates, threshold)
        if result is not None:
            assert result.candidate in candidates
            assert 0 <= result.score <= 100

    @given(description=_descriptions, candidates=st.lists(_candidate_strategy(), max_size=20))
    def test_higher_threshold_never_yields_more_permissive_result(self, description, candidates):
        """Property: raising the threshold can only ever exclude matches, never include more."""
        loose = _find_best_match(description, candidates, threshold=0)
        strict = _find_best_match(description, candidates, threshold=100)
        if strict is not None:
            assert loose is not None
            assert strict.score >= loose.score or strict.score == 100

    @given(description=_descriptions)
    def test_empty_candidate_list_never_matches(self, description):
        assert _find_best_match(description, [], threshold=0) is None

    @given(description=_descriptions, candidates=st.lists(_candidate_strategy(), min_size=1, max_size=20))
    def test_all_scores_below_threshold_yields_none(self, description, candidates):
        # threshold=101 is unreachable (scores are 0-100), so nothing can ever qualify
        assert _find_best_match(description, candidates, threshold=101) is None

    def test_exact_match_scores_100(self):
        candidate = SimilarityCandidate(
            transaction_id="t1",
            description="NTUC FAIRPRICE",
            category_name="Groceries",
            category_source="llm",
            amount=_FIXED_AMOUNT,
        )
        result = _find_best_match("NTUC FAIRPRICE", [candidate], threshold=50)
        assert result is not None
        assert result.score == 100

    def test_manual_precedence_over_higher_scoring_non_manual(self):
        """WR-3: a manual match wins even if a non-manual candidate scores higher."""
        manual = SimilarityCandidate(
            transaction_id="m1",
            description="STARBUCKS COFFEE SG",
            category_name="Dining",
            category_source="manual",
            amount=_FIXED_AMOUNT,
        )
        higher_scoring_llm = SimilarityCandidate(
            transaction_id="l1",
            description="STARBUCKS",
            category_name="Entertainment",
            category_source="llm",
            amount=_FIXED_AMOUNT,
        )
        result = _find_best_match("STARBUCKS COFFEE", [manual, higher_scoring_llm], threshold=50)
        assert result is not None
        assert result.candidate.category_source == "manual"
        assert result.candidate.category_name == "Dining"

    def test_no_manual_candidate_falls_back_to_highest_scoring(self):
        similarity_match = SimilarityCandidate(
            transaction_id="s1",
            description="GRAB RIDE",
            category_name="Transport",
            category_source="similarity",
            amount=_FIXED_AMOUNT,
        )
        llm_match = SimilarityCandidate(
            transaction_id="l1", description="GRAB", category_name="Others", category_source="llm", amount=_FIXED_AMOUNT
        )
        result = _find_best_match("GRAB RIDE HOME", [similarity_match, llm_match], threshold=30)
        assert result is not None
        assert result.candidate.transaction_id == "s1"  # closer textual match, no manual present


class TestAmountRangeGating:
    """Regression coverage for a real incident: two OCBC "FAST PAYMENT via
    PayNow-UEN to AXS PTE. LTD." transactions -- AXS is a bill-payment kiosk used
    for many unrelated bill types -- had near-identical description text but wildly
    different amounts ($699 a car loan installment, $81.70 a conservancy fee).
    Correcting one surfaced the other as a suggested match purely on text
    similarity. See aidlc-docs/audit.md 2026-08-06."""

    # The two exact transaction reference numbers the user reported
    # ("...251129591611147661" and "...260201413718399401") only score 84.29 via
    # rapidfuzz token_sort_ratio -- just under the app's default similarity_threshold
    # of 85 -- so they wouldn't be text-eligible at all in isolation (verified by
    # actually running rapidfuzz, not assumed). The real, live-database mechanism
    # (confirmed by querying the account's actual 24+ AXS transactions) is that
    # SOME reference-number pairs among many do cross the threshold and, once one
    # is mismatched, itself becomes a bad precedent for the next -- a slow
    # cross-contamination across the whole history. A single-digit-different
    # reference (below) reproduces that in miniature: 98.57, comfortably above both
    # similarity_threshold (85) and recategorization_auto_apply_threshold (97).
    _AXS_DESCRIPTION = "FAST PAYMENT via PayNow-UEN to AXS PTE. LTD. OTHR - 251129591611147661"
    _AXS_DESCRIPTION_OTHER_REF = "FAST PAYMENT via PayNow-UEN to AXS PTE. LTD. OTHR - 251129591611147662"

    def test_same_merchant_wildly_different_amount_does_not_match(self):
        """The reported case in miniature: near-identical AXS reference numbers
        (real mechanism: some pairs among many score this closely), $699 car loan
        vs $81.70 conservancy fee."""
        car_loan_candidate = SimilarityCandidate(
            transaction_id="c1",
            description=self._AXS_DESCRIPTION,
            category_name="Car Loan",
            category_source="manual",
            amount=Decimal("699.00"),
        )
        result = find_best_match(
            self._AXS_DESCRIPTION_OTHER_REF,
            Decimal("81.70"),
            [car_loan_candidate],
            threshold=85,
            amount_ratio_tolerance=4.0,
            amount_absolute_floor=Decimal("5.00"),
        )
        assert result is None

    def test_same_merchant_similar_amount_still_matches(self):
        """A legitimate near-duplicate (e.g. two car loan installments a month
        apart) must still match -- the gate targets wildly different amounts, not
        any variance at all."""
        car_loan_candidate = SimilarityCandidate(
            transaction_id="c1",
            description=self._AXS_DESCRIPTION,
            category_name="Car Loan",
            category_source="manual",
            amount=Decimal("699.00"),
        )
        result = find_best_match(
            self._AXS_DESCRIPTION_OTHER_REF,
            Decimal("705.00"),
            [car_loan_candidate],
            threshold=85,
            amount_ratio_tolerance=4.0,
            amount_absolute_floor=Decimal("5.00"),
        )
        assert result is not None
        assert result.candidate.category_name == "Car Loan"

    def test_small_value_line_items_match_via_absolute_floor_despite_large_ratio(self):
        """Two currency-conversion fees of $0.01 and $0.27 -- a 27x ratio, but
        trivially close in real terms -- must still match via the absolute floor."""
        fee_candidate = SimilarityCandidate(
            transaction_id="f1",
            description="CCY CONVERSION FEE FOR: 1.48 SGD",
            category_name="Bank charges",
            category_source="manual",
            amount=Decimal("0.01"),
        )
        result = find_best_match(
            "CCY CONVERSION FEE FOR: 26.86 SGD",
            Decimal("0.27"),
            [fee_candidate],
            threshold=85,
            amount_ratio_tolerance=4.0,
            amount_absolute_floor=Decimal("5.00"),
        )
        assert result is not None

    def test_ratio_just_over_tolerance_excluded_just_under_included(self):
        candidate = SimilarityCandidate(
            transaction_id="c1", description="SOME MERCHANT", category_name="Bills", category_source="manual",
            amount=Decimal("100.00"),
        )
        # 4.0x tolerance: $400 is exactly at the boundary (included), $400.01 just over.
        at_boundary = find_best_match(
            "SOME MERCHANT", Decimal("400.00"), [candidate], threshold=85,
            amount_ratio_tolerance=4.0, amount_absolute_floor=Decimal("5.00"),
        )
        just_over = find_best_match(
            "SOME MERCHANT", Decimal("400.01"), [candidate], threshold=85,
            amount_ratio_tolerance=4.0, amount_absolute_floor=Decimal("5.00"),
        )
        assert at_boundary is not None
        assert just_over is None

    def test_text_match_alone_is_not_enough_when_amount_gate_fails(self):
        """An exact text match (score 100) is still excluded if the amounts are
        out of range -- the amount gate is a hard AND, not folded into the score."""
        candidate = SimilarityCandidate(
            transaction_id="c1", description="IDENTICAL TEXT", category_name="Car Loan", category_source="manual",
            amount=Decimal("699.00"),
        )
        result = find_best_match(
            "IDENTICAL TEXT", Decimal("81.70"), [candidate], threshold=85,
            amount_ratio_tolerance=4.0, amount_absolute_floor=Decimal("5.00"),
        )
        assert result is None


class TestNormalizeReferenceNoise:
    """WR-20: reference-code-shaped noise is stripped before fuzzy scoring, so a
    repeat payment to the same payee isn't blocked from matching purely by a unique
    per-transaction reference code. See aidlc-docs/audit.md 2026-08-11."""

    def test_strips_long_digit_run(self):
        result = normalize_reference_noise(
            "FAST PAYMENT via PayNow-UEN to NEO EMPIRE PTE. OTHR-260102595543212111."
        )
        assert "260102595543212111" not in result
        assert "NEO EMPIRE PTE" in result

    def test_strips_short_mixed_alphanumeric_tokens(self):
        result = normalize_reference_noise(
            "FUND TRANSFER via PayNow-QR Code to WARBURG VENDING OTHR-QR3 dy01qkET 00747"
        )
        assert "QR3" not in result
        assert "dy01qkET" not in result
        assert "00747" not in result
        assert "WARBURG VENDING" in result

    def test_leaves_description_with_no_reference_code_unchanged_in_content(self):
        result = normalize_reference_noise("FUND TRANSFER via PayNow-QR Code to CHANG WAI YEE OTHR - OTHR")
        assert "CHANG WAI YEE" in result
        assert "OTHR" in result

    def test_short_digit_only_token_is_not_stripped(self):
        """A single- or double-digit token (e.g. from a real merchant name like
        "7-ELEVEN") is not a reference-code shape (needs 3+ consecutive digits, or a
        letter+digit mix) and must survive untouched."""
        result = normalize_reference_noise("PAYMENT TO 7-ELEVEN")
        assert "7" in result
        assert "ELEVEN" in result

    def test_does_not_touch_decimal_amounts_embedded_in_description(self):
        result = normalize_reference_noise("CCY CONVERSION FEE FOR: 26.86 SGD")
        assert "26.86" in result

    @given(description=_descriptions)
    def test_never_lengthens_the_string(self, description):
        assert len(normalize_reference_noise(description)) <= len(description)

    @given(description=_descriptions)
    def test_idempotent(self, description):
        once = normalize_reference_noise(description)
        twice = normalize_reference_noise(once)
        assert once == twice


class TestFindBestMatchReferenceCodeNoise:
    """WR-20 regression coverage: the 3 diagnosis examples, re-run as same-payee
    repeat-payment pairs (same payee, different reference/QR code, amount held in
    range), must now clear `similarity_threshold` -- reproducing the reported fix
    live against the project's actual rapidfuzz dependency, not assumed."""

    def _assert_same_payee_pair_matches(self, description_a: str, description_b: str) -> None:
        candidate = SimilarityCandidate(
            transaction_id="c1",
            description=description_a,
            category_name="Dining",
            category_source="manual",
            amount=_FIXED_AMOUNT,
        )
        result = find_best_match(
            description_b, _FIXED_AMOUNT, [candidate], threshold=85.0,
            amount_ratio_tolerance=_RATIO_TOLERANCE, amount_absolute_floor=_ABSOLUTE_FLOOR,
        )
        assert result is not None
        assert result.score >= 85.0

    def test_neo_empire_repeat_payment_now_matches(self):
        self._assert_same_payee_pair_matches(
            "FAST PAYMENT via PayNow-UEN to NEO EMPIRE PTE. OTHR-260102595543212111.",
            "FAST PAYMENT via PayNow-UEN to NEO EMPIRE PTE. OTHR-987654321012345678.",
        )

    def test_warburg_vending_repeat_payment_now_matches(self):
        self._assert_same_payee_pair_matches(
            "FUND TRANSFER via PayNow-QR Code to WARBURG VENDING OTHR-QR3 dy01qkET 00747",
            "FUND TRANSFER via PayNow-QR Code to WARBURG VENDING OTHR-QR9 zz88abCD 11111",
        )

    def test_chang_wai_yee_repeat_payment_now_matches(self):
        self._assert_same_payee_pair_matches(
            "FUND TRANSFER via PayNow-QR Code to CHANG WAI YEE OTHR - OTHR",
            "FUND TRANSFER via PayNow-QR Code to CHANG WAI YEE OTHR - OTHR",
        )

    def test_different_payees_still_do_not_match(self):
        """Cross-payee sanity check: normalization must not cause unrelated payees
        to fuzzy-match as the same (FR-3)."""
        candidate = SimilarityCandidate(
            transaction_id="c1",
            description="FUND TRANSFER via PayNow-QR Code to CHANG WAI YEE OTHR - OTHR",
            category_name="Dining",
            category_source="manual",
            amount=_FIXED_AMOUNT,
        )
        result = find_best_match(
            "FAST PAYMENT via PayNow-UEN to NEO EMPIRE PTE. OTHR-260102595543212111.",
            _FIXED_AMOUNT, [candidate], threshold=85.0,
            amount_ratio_tolerance=_RATIO_TOLERANCE, amount_absolute_floor=_ABSOLUTE_FLOOR,
        )
        assert result is None
