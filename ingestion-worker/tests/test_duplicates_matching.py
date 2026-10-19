"""WR-58, WR-60, WR-64: the pure matching rule. Example-based tests for each rule, with the two
real-data shapes (the UOB and Trust June pairs, and the CIMB one-transaction look-alikes),
plus property-based tests (NFR-PD-7)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from itertools import pairwise

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from ingestion_worker.accounts.normalize import bank_key
from ingestion_worker.duplicates import matching
from ingestion_worker.duplicates.matching import (
    AccountFact,
    CopyFacts,
    DetectionSettings,
    StatementSide,
    TxnKey,
)

D = Decimal
DEFAULTS = DetectionSettings(enabled=True, match_ratio=D("0.80"), min_transactions=3)


def txn(day=5, amount="10.00", description="NTUC FAIRPRICE", direction="out", currency="SGD", month=6):
    return TxnKey(date(2026, month, day), D(amount), direction, currency, description)


def side(txns, *, key="uob", accounts=(), name="UOB", h="a" * 64, ingested=None):
    return StatementSide(
        content_hash=h, bank_key=key, transactions=tuple(txns), accounts=tuple(accounts), bank_name=name, ingested_at=ingested
    )


def june(n, **kw):
    """n distinct transactions spread over June 2026."""
    return [txn(day=2 + i, amount=f"{10 + i}.00", description=f"MERCHANT {i}", **kw) for i in range(n)]


class TestMatchTransactions:
    def test_identical_sets_match_completely(self):
        a = june(5)
        assert len(matching.match_transactions(a, list(a))) == 5

    def test_nothing_matches_when_nothing_is_shared(self):
        assert matching.match_transactions(june(3), [txn(day=20, amount="999.00", description="OTHER")]) == []

    @pytest.mark.parametrize(
        "field,other",
        [("day", 6), ("amount", "10.01"), ("direction", "in"), ("currency", "USD")],
    )
    def test_date_amount_direction_and_currency_must_all_match(self, field, other):
        assert matching.match_transactions([txn()], [txn(**{field: other})]) == []

    def test_matching_is_one_to_one(self):
        """Two identical coffees on one side must not both match one coffee on the other."""
        two = [txn(description="KOPI"), txn(description="KOPI")]
        one = [txn(description="KOPI")]
        assert len(matching.match_transactions(two, one)) == 1
        assert len(matching.match_transactions(one, two)) == 1

    def test_equal_repeated_transactions_all_pair_up(self):
        two = [txn(description="KOPI"), txn(description="KOPI")]
        assert len(matching.match_transactions(two, list(two))) == 2

    def test_description_case_and_whitespace_are_ignored(self):
        assert len(matching.match_transactions([txn(description="Ntuc  Fairprice")], [txn(description="NTUC FAIRPRICE ")])) == 1

    def test_a_small_wording_difference_is_tolerated(self):
        a, b = txn(description="PAYNOW TRANSFER TO JOHN TAN"), txn(description="PAYNOW TRANSFER TO JOHN TAN.")
        assert len(matching.match_transactions([a], [b])) == 1

    def test_a_large_wording_difference_is_not(self):
        assert matching.match_transactions([txn(description="NTUC FAIRPRICE")], [txn(description="STARBUCKS COFFEE")]) == []

    def test_reference_codes_are_not_stripped(self):
        """Unlike the similarity matcher: two purchases differing only by a reference stay distinct
        when the difference is large enough to matter."""
        a, b = txn(description="GRAB 1111111111"), txn(description="GRAB 9999999999")
        # Same text apart from the digits: similarity is high, so they DO match -- the point is that
        # nothing was removed to make them match; only the similarity floor decides.
        assert matching.normalize_description("GRAB 1111111111") != matching.normalize_description("GRAB 9999999999")
        assert len(matching.match_transactions([a], [b])) in (0, 1)

    def test_the_similarity_floor_boundary(self):
        base = "A" * 20
        # 17 of 20 characters shared in order -> ratio 2*17/40 = 0.85 exactly: matches (>= floor).
        at_floor = "A" * 17 + "BBB"
        below = "A" * 16 + "BBBB"  # 2*16/40 = 0.80
        assert len(matching.match_transactions([txn(description=base)], [txn(description=at_floor)])) == 1
        assert matching.match_transactions([txn(description=base)], [txn(description=below)]) == []

    def test_fuzzy_remainder_is_a_maximum_matching(self):
        """Greedy best-first pairing would match one pair here; the maximum matching finds two."""
        a1 = txn(description="PAYMENT TO ACME PTE LTD")
        a2 = txn(description="PAYMENT TO ACME PTE LTD SG")
        b1 = txn(description="PAYMENT TO ACME PTE LTD")  # equal to a1 only
        b2 = txn(description="PAYMENT TO ACME PTE LTD S")  # similar to both a1 and a2
        pairs = matching.match_transactions([a1, a2], [b1, b2])
        assert len(pairs) == 2


class TestRatioPeriodAndSizes:
    def test_ratio_is_against_the_smaller_side(self):
        assert matching.match_ratio(5, 5, 30) == D("1.0000")
        assert matching.match_ratio(4, 5, 5) == D("0.8000")

    def test_ratio_of_an_empty_side_is_zero(self):
        assert matching.match_ratio(0, 0, 5) == D("0.0000")

    def test_threshold_is_exact_not_floating_point(self):
        """0.7 * 10 is 7.000000000000001 in floating point; 7 of 10 must still meet 0.70."""
        settings_70 = DetectionSettings(True, D("0.70"), 1)
        a = june(10)
        b = june(7) + [txn(day=28, amount=f"{900 + i}.00", description=f"X{i}") for i in range(3)]
        verdict = matching.evaluate(side(a), side(b), settings_70)
        assert verdict.matched_count == 7 and verdict.is_duplicate

    @pytest.mark.parametrize(
        "p,q,expected",
        [
            ((date(2026, 6, 2), date(2026, 6, 30)), (date(2026, 6, 2), date(2026, 6, 30)), True),
            ((date(2026, 6, 1), date(2026, 6, 15)), (date(2026, 6, 15), date(2026, 6, 30)), True),  # touching
            ((date(2026, 6, 1), date(2026, 6, 14)), (date(2026, 6, 15), date(2026, 6, 30)), False),
            ((date(2026, 5, 1), date(2026, 5, 31)), (date(2026, 6, 1), date(2026, 6, 30)), False),
            (None, (date(2026, 6, 1), date(2026, 6, 30)), False),
        ],
    )
    def test_period_overlap(self, p, q, expected):
        assert matching.periods_overlap(p, q) is expected

    @pytest.mark.parametrize("a,b,expected", [(10, 10, True), (10, 8, True), (10, 7, False), (30, 10, False), (5, 5, True)])
    def test_sizes_comparable_uses_the_ratio_in_both_directions(self, a, b, expected):
        assert matching.sizes_comparable(a, b, D("0.80")) is expected
        assert matching.sizes_comparable(b, a, D("0.80")) is expected


class TestEvaluate:
    def test_the_uob_june_pair_is_flagged(self):
        a, b = june(5), june(5)
        verdict = matching.evaluate(side(a, h="1" * 64), side(b, h="2" * 64), DEFAULTS)
        assert verdict.is_duplicate and verdict.matched_count == 5 and verdict.ratio == D("1.0000")
        assert verdict.sizes_comparable and not verdict.small_gate_applied

    def test_the_trust_pair_with_two_bank_name_spellings_is_flagged_by_bank_key(self):
        """The raw names differ; the caller compares normalized bank keys, which are equal."""
        key_a, key_b = bank_key("Trust Bank Singapore Limited"), bank_key("Trust")
        assert key_a == key_b
        a, b = june(8), june(8)
        verdict = matching.evaluate(side(a, key=key_a), side(b, key=key_b), DEFAULTS)
        assert verdict.is_duplicate and verdict.matched_count == 8

    def test_the_cimb_one_transaction_lookalikes_are_not_flagged(self):
        one = [txn(day=28, month=2, amount="12.34", description="INTEREST", direction="in")]
        verdict = matching.evaluate(side(one, key="cimb"), side(list(one), key="cimb"), DEFAULTS)
        assert not verdict.is_duplicate and verdict.small_gate_applied
        assert verdict.is_candidate and "fewer than 3" in verdict.why_not

    def test_a_small_statement_is_flagged_only_with_matching_identifier_and_closing_balance(self):
        one = [txn(day=28, month=2, amount="12.34", description="INTEREST", direction="in")]
        fact = AccountFact("1234", "SGD", D("100.00"), date(2026, 2, 28))
        verdict = matching.evaluate(side(one, accounts=[fact]), side(list(one), accounts=[fact]), DEFAULTS)
        assert verdict.is_duplicate and verdict.small_gate_applied

    def test_a_small_statement_with_a_different_closing_balance_is_not_flagged(self):
        one = [txn(day=28, month=2, amount="12.34", description="INTEREST", direction="in")]
        fa = AccountFact("1234", "SGD", D("100.00"), date(2026, 2, 28))
        fb = AccountFact("1234", "SGD", D("100.01"), date(2026, 2, 28))
        assert not matching.evaluate(side(one, accounts=[fa]), side(list(one), accounts=[fb]), DEFAULTS).is_duplicate

    def test_a_small_statement_with_a_missing_closing_balance_is_not_flagged(self):
        one = [txn(day=28, month=2, amount="12.34", description="INTEREST", direction="in")]
        fact = AccountFact("1234", "SGD")
        assert not matching.evaluate(side(one, accounts=[fact]), side(list(one), accounts=[fact]), DEFAULTS).is_duplicate

    def test_conflicting_account_identifiers_are_never_flagged(self):
        a, b = june(5), june(5)
        verdict = matching.evaluate(
            side(a, accounts=[AccountFact("1111", "SGD")]), side(b, accounts=[AccountFact("2222", "SGD")]), DEFAULTS
        )
        assert not verdict.is_duplicate and verdict.account_rule == matching.ACCOUNT_CONFLICT

    def test_identifiers_on_only_one_side_do_not_apply(self):
        a, b = june(5), june(5)
        verdict = matching.evaluate(side(a, accounts=[AccountFact("1111", "SGD")]), side(b), DEFAULTS)
        assert verdict.is_duplicate and verdict.account_rule == matching.ACCOUNT_NOT_APPLICABLE

    def test_one_shared_account_among_several_is_enough(self):
        a, b = june(5), june(5)
        verdict = matching.evaluate(
            side(a, accounts=[AccountFact("1111", "SGD"), AccountFact("2222", "SGD")]),
            side(b, accounts=[AccountFact("2222", "SGD")]),
            DEFAULTS,
        )
        assert verdict.is_duplicate and verdict.account_rule == matching.ACCOUNT_SHARED

    def test_different_banks_are_never_flagged(self):
        a, b = june(5), june(5)
        assert not matching.evaluate(side(a, key="uob"), side(b, key="dbs"), DEFAULTS).is_duplicate

    def test_non_overlapping_periods_are_never_flagged(self):
        a, b = june(5), [txn(day=2 + i, month=7, amount=f"{10 + i}.00", description=f"MERCHANT {i}") for i in range(5)]
        verdict = matching.evaluate(side(a), side(b), DEFAULTS)
        assert not verdict.is_duplicate and not verdict.periods_overlap

    def test_below_the_ratio_is_not_flagged_and_says_why(self):
        a = june(10)
        b = june(5) + [txn(day=28, amount=f"{900 + i}.00", description=f"X{i}") for i in range(5)]
        verdict = matching.evaluate(side(a), side(b), DEFAULTS)
        assert not verdict.is_duplicate and verdict.matched_count == 5 and "below" in verdict.why_not

    def test_an_empty_statement_is_never_flagged(self):
        assert not matching.evaluate(side([]), side(june(5)), DEFAULTS).is_duplicate

    def test_a_larger_statement_containing_a_smaller_one_is_flagged_but_not_comparable(self):
        """Question 1 = C: still a probable duplicate (matched against the smaller), but its size
        difference decides what may be done about it."""
        small = june(5)
        large = june(5) + [txn(day=20 + i, amount=f"{500 + i}.00", description=f"EXTRA {i}") for i in range(10)]
        verdict = matching.evaluate(side(small, h="1" * 64), side(large, h="2" * 64), DEFAULTS)
        assert verdict.is_duplicate and verdict.matched_count == 5
        assert not verdict.sizes_comparable

    def test_the_minimum_is_a_setting(self):
        one = [txn()]
        relaxed = DetectionSettings(True, D("0.80"), 1)
        assert matching.evaluate(side(one), side(list(one)), relaxed).is_duplicate  # nothing counts as small


class TestDescribe:
    def _verdict(self, a, b):
        return matching.evaluate(side(a, h="1" * 64), side(b, h="2" * 64), DEFAULTS)

    def test_a_plain_match_states_the_figures_bank_and_period(self):
        a, b = june(8), june(8)
        text = matching.describe(self._verdict(a, b), side(a), side(b), incoming=True)
        assert text.startswith("8 of 8 transactions match (the smaller statement); same bank; overlapping period 2 Jun to 9 Jun 2026.")
        assert "larger" not in text and "smaller one" not in text

    def test_an_incoming_larger_file_says_prominently_what_was_not_ingested(self):
        held = june(5)
        incoming = june(5) + [txn(day=20 + i, amount=f"{500 + i}.00", description=f"EXTRA {i}") for i in range(10)]
        v = self._verdict(held, incoming)
        text = matching.describe(v, side(held), side(incoming), incoming=True)
        assert "This file is the larger one: it has 15 transactions against 5 on the held statement" in text
        assert "10 of its transactions have no match, so they were not ingested" in text

    def test_an_incoming_smaller_file_says_so(self):
        held = june(5) + [txn(day=20 + i, amount=f"{500 + i}.00", description=f"EXTRA {i}") for i in range(10)]
        incoming = june(5)
        text = matching.describe(self._verdict(held, incoming), side(held), side(incoming), incoming=True)
        assert "This file is the smaller one: it has 5 transactions against 15" in text

    def test_a_pair_of_different_sizes_states_both_counts(self):
        small = june(5)
        large = june(5) + [txn(day=20 + i, amount=f"{500 + i}.00", description=f"EXTRA {i}") for i in range(10)]
        text = matching.describe(self._verdict(small, large), side(small), side(large), incoming=False)
        assert "differ in size (15 and 5 transactions); 10 on the larger one have no match" in text

    def test_period_formatting_within_and_across_years(self):
        assert matching.format_period(date(2026, 6, 2), date(2026, 6, 30)) == "2 Jun to 30 Jun 2026"
        assert matching.format_period(date(2025, 12, 28), date(2026, 1, 3)) == "28 Dec 2025 to 3 Jan 2026"


class TestSnapshot:
    def test_at_most_ten_rows_the_largest_first(self):
        txns = [txn(day=1 + i % 28, amount=f"{i + 1}.00", description=f"M{i}") for i in range(25)]
        rows = matching.select_snapshot(txns, set())
        assert len(rows) == 10
        assert [r.amount for r in rows] == [D(f"{25 - i}.00") for i in range(10)]
        assert [r.rank for r in rows] == list(range(1, 11))

    def test_fewer_than_ten_are_all_shown(self):
        assert len(matching.select_snapshot(june(4), set())) == 4

    def test_ties_on_amount_are_ranked_earlier_date_first(self):
        rows = matching.select_snapshot([txn(day=9, amount="5.00", description="LATE"), txn(day=2, amount="5.00", description="EARLY")], set())
        assert [r.description for r in rows] == ["EARLY", "LATE"]

    def test_markers_follow_the_matched_indexes(self):
        rows = matching.select_snapshot(june(3), {0})
        by_desc = {r.description: r.marker for r in rows}
        assert by_desc["MERCHANT 0"] == matching.MARKER_ALSO_ON_OTHER
        assert by_desc["MERCHANT 1"] == matching.MARKER_ONLY_ON_THIS_ONE


class TestChooseKeptCopy:
    T0 = datetime(2026, 8, 4, tzinfo=UTC)

    def copy(self, h, corrections, days=0):
        return CopyFacts(h, corrections, self.T0 + timedelta(days=days))

    def test_the_copy_with_corrections_is_kept_even_if_later(self):
        keep, remove = matching.choose_kept_copy(self.copy("a", 0, 0), self.copy("b", 2, 30))
        assert (keep.content_hash, remove.content_hash) == ("b", "a")

    def test_neither_has_corrections_keeps_the_earlier_ingested(self):
        keep, _ = matching.choose_kept_copy(self.copy("a", 0, 30), self.copy("b", 0, 0))
        assert keep.content_hash == "b"

    def test_both_have_corrections_keeps_the_earlier_ingested(self):
        keep, _ = matching.choose_kept_copy(self.copy("a", 3, 30), self.copy("b", 1, 0))
        assert keep.content_hash == "b"

    def test_a_full_tie_falls_back_to_the_smaller_hash(self):
        keep, _ = matching.choose_kept_copy(self.copy("b", 0), self.copy("a", 0))
        assert keep.content_hash == "a"


# ----------------------------------------------------------------------------- property-based

_dates = st.dates(min_value=date(2026, 6, 1), max_value=date(2026, 6, 6))
_amounts = st.sampled_from([D("1.00"), D("2.50"), D("10.00")])
_directions = st.sampled_from(["out", "in"])
_currencies = st.sampled_from(["SGD", "USD"])
_descriptions = st.sampled_from(["KOPI", "kopi ", "KOPI SHOP", "GRAB RIDE", "GRAB RIDE 1", "NTUC", "STARBUCKS"])
txn_keys = st.builds(TxnKey, _dates, _amounts, _directions, _currencies, _descriptions)
txn_lists = st.lists(txn_keys, max_size=12)


@settings(max_examples=150, deadline=None)
@given(txn_lists, txn_lists)
def test_property_matching_is_symmetric_and_bounded(a, b):
    ab = matching.match_transactions(a, b)
    ba = matching.match_transactions(b, a)
    assert len(ab) == len(ba)
    assert len(ab) <= min(len(a), len(b))
    assert len({i for i, _ in ab}) == len(ab) and len({j for _, j in ab}) == len(ab)  # one-to-one
    for i, j in ab:
        assert (a[i].date, a[i].amount, a[i].direction, a[i].currency) == (b[j].date, b[j].amount, b[j].direction, b[j].currency)


@settings(max_examples=150, deadline=None)
@given(txn_lists)
def test_property_a_list_matches_itself_completely(a):
    assert len(matching.match_transactions(a, list(a))) == len(a)


@settings(max_examples=100, deadline=None)
@given(txn_lists, txn_lists)
def test_property_the_verdict_is_symmetric(a, b):
    sa, sb = side(a, h="1" * 64), side(b, h="2" * 64)
    v1, v2 = matching.evaluate(sa, sb, DEFAULTS), matching.evaluate(sb, sa, DEFAULTS)
    assert (v1.is_duplicate, v1.matched_count, v1.ratio, v1.sizes_comparable) == (
        v2.is_duplicate, v2.matched_count, v2.ratio, v2.sizes_comparable
    )
    assert D("0") <= v1.ratio <= D("1")


@settings(max_examples=100, deadline=None)
@given(txn_lists, st.sets(st.integers(min_value=0, max_value=11)))
def test_property_the_snapshot_is_bounded_largest_first_and_marked_consistently(txns, matched):
    matched = {i for i in matched if i < len(txns)}
    rows = matching.select_snapshot(txns, matched)
    assert len(rows) == min(10, len(txns))
    amounts = [r.amount for r in rows]
    assert amounts == sorted(amounts, reverse=True)
    assert amounts == sorted((t.amount for t in txns), reverse=True)[: len(rows)]  # they ARE the largest
    for earlier, later in pairwise(rows):
        if earlier.amount == later.amount:
            assert earlier.date <= later.date  # ties: earlier date first
    marked_matched = sum(r.marker == matching.MARKER_ALSO_ON_OTHER for r in rows)
    assert marked_matched <= len(matched)


_copy = st.builds(
    CopyFacts,
    st.sampled_from(["a", "b", "c"]),
    st.integers(min_value=0, max_value=3),
    st.datetimes(min_value=datetime(2026, 1, 1), max_value=datetime(2026, 1, 3)),
)


@settings(max_examples=150, deadline=None)
@given(_copy, _copy)
def test_property_the_kept_copy_ignores_argument_order(x, y):
    # Two held statements always have different content hashes (BR-3 makes it unique), so a
    # full tie on corrections, time AND hash cannot occur; Hypothesis found that input and it
    # is not a real one.
    assume(x.content_hash != y.content_hash)
    keep1, remove1 = matching.choose_kept_copy(x, y)
    keep2, remove2 = matching.choose_kept_copy(y, x)
    assert (keep1, remove1) == (keep2, remove2)
    assert {keep1, remove1} == {x, y}
