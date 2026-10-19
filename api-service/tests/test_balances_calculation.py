"""The pure balance arithmetic (AR-55, AR-56, AR-57, AR-59, AR-61, AR-62): properties first (NFR-AB-4, PBT-02/03), then
the date, rounding and tie rules by example."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from balance_strategies import (
    calendar_dates,
    date_ranges,
    dated_flows,
    known_balance_sets,
    known_balances,
    money,
)
from hypothesis import assume, given
from hypothesis import strategies as st

from api_service.balances import calculation as calc
from api_service.balances.calculation import (
    ANCHOR,
    STATEMENT_CLOSING,
    KnownBalance,
    NetFlowIndex,
)


def anchor(balance="100.00", day=date(2026, 6, 30)):
    return KnownBalance(Decimal(balance), day, ANCHOR)


def closing(balance, day, n=1, order=0):
    return KnownBalance(Decimal(balance), day, STATEMENT_CLOSING, UUID(int=n), order)


def places(value: Decimal) -> int:
    return -value.as_tuple().exponent


# ----------------------------------------------------------------------------------------------------- properties


class TestBalanceProperties:
    @given(known_balances(), dated_flows())
    def test_the_balance_on_the_known_date_is_the_known_balance(self, known, flows):
        balance, reference = calc.balance_on_date([known], known.date, NetFlowIndex(flows).net)
        assert balance == known.balance and reference == known

    @given(known_balances(), calendar_dates(), dated_flows())
    def test_working_forward_then_back_returns_the_start(self, known, target, flows):
        net = NetFlowIndex(flows).net
        there, _ = calc.balance_on_date([known], target, net)
        back, _ = calc.balance_on_date([KnownBalance(there, target, ANCHOR)], known.date, net)
        assert back == known.balance

    @given(known_balances(), st.lists(st.integers(min_value=0, max_value=500), min_size=3, max_size=3), dated_flows())
    def test_after_the_known_date_balances_differ_by_the_net_flow_between_them(self, known, offsets, flows):
        a, b, c = (known.date + timedelta(days=o) for o in sorted(offsets))
        net = NetFlowIndex(flows).net
        at = lambda d: calc.balance_on_date([known], d, net)[0]  # noqa: E731
        assert at(c) - at(b) == net(b, c)
        assert at(b) - at(a) == net(a, b)

    @given(known_balances(), st.lists(st.integers(min_value=0, max_value=500), min_size=3, max_size=3), dated_flows())
    def test_before_the_known_date_balances_differ_by_the_net_flow_between_them(self, known, offsets, flows):
        a, b, c = (known.date - timedelta(days=o) for o in sorted(offsets, reverse=True))
        net = NetFlowIndex(flows).net
        at = lambda d: calc.balance_on_date([known], d, net)[0]  # noqa: E731
        assert at(c) - at(b) == net(b, c)
        assert at(b) - at(a) == net(a, b)

    @given(known_balances(), calendar_dates(), dated_flows())
    def test_every_balance_is_an_exact_two_place_decimal(self, known, target, flows):
        balance, _ = calc.balance_on_date([known], target, NetFlowIndex(flows).net)
        assert isinstance(balance, Decimal) and balance.is_finite() and places(balance) <= 2

    @given(dated_flows(), calendar_dates(), calendar_dates())
    def test_the_index_agrees_with_adding_up_the_days(self, flows, after, through):
        expected = sum((v for d, v in flows.items() if after < d <= through), Decimal(0))
        assert NetFlowIndex(flows).net(after, through) == expected

    @given(dated_flows(), calendar_dates(), calendar_dates(), calendar_dates())
    def test_net_flow_adds_up_across_a_split_date(self, flows, x, y, z):
        a, b, c = sorted([x, y, z])
        index = NetFlowIndex(flows)
        assert index.net(a, c) == index.net(a, b) + index.net(b, c)


class TestChooseReferenceProperties:
    @given(known_balance_sets(), calendar_dates())
    def test_the_reference_is_never_farther_than_another_known_balance(self, known, target):
        chosen = calc.choose_reference(known, target)
        assert all(abs((chosen.date - target).days) <= abs((k.date - target).days) for k in known)

    @given(known_balance_sets(min_size=2), calendar_dates(), st.randoms(use_true_random=False))
    def test_the_choice_does_not_depend_on_the_order_of_the_input(self, known, target, rng):
        shuffled = list(known)
        rng.shuffle(shuffled)
        assert calc.choose_reference(known, target) == calc.choose_reference(shuffled, target)

    @given(calendar_dates(), st.integers(min_value=1, max_value=200), money(), money(), money())
    def test_an_anchor_wins_a_tie_with_a_printed_balance(self, target, days, a, b, c):
        manual = KnownBalance(a, target - timedelta(days=days), ANCHOR)
        printed = closing(b, target + timedelta(days=days))
        assert calc.choose_reference([printed, manual], target) == manual
        assert calc.choose_reference([manual, printed], target) == manual

    @given(calendar_dates(), st.integers(min_value=1, max_value=200), money(), money())
    def test_between_two_printed_balances_an_exact_tie_goes_to_the_earlier_date(self, target, days, a, b):
        earlier = closing(a, target - timedelta(days=days), n=1)
        later = closing(b, target + timedelta(days=days), n=2)
        assert calc.choose_reference([later, earlier], target) == earlier

    @given(known_balance_sets(max_size=10))
    def test_there_is_at_most_one_known_balance_per_date_and_an_anchor_is_never_lost(self, known):
        deduped = calc.deduplicate_by_date(known)
        assert len({k.date for k in deduped}) == len(deduped) == len({k.date for k in known})
        assert [k.date for k in deduped] == sorted(k.date for k in deduped)
        for k in deduped:
            if any(x.source == ANCHOR and x.date == k.date for x in known):
                assert k.source == ANCHOR


class TestSeriesProperties:
    @given(date_ranges(), st.sampled_from([calc.DAY, calc.MONTH]))
    def test_every_plotted_date_lies_in_the_range_in_order_without_repeats(self, bounds, granularity):
        start, end = bounds
        dates = calc.series_dates(start, end, granularity)
        assert dates == sorted(set(dates)) and dates[-1] == end
        assert all(start <= d <= end for d in dates)

    @given(date_ranges(max_days=400))
    def test_a_daily_series_has_every_day_exactly_once(self, bounds):
        start, end = bounds
        assert len(calc.series_dates(start, end, calc.DAY)) == (end - start).days + 1

    @given(date_ranges())
    def test_a_monthly_series_is_month_ends_plus_the_range_end(self, bounds):
        start, end = bounds
        dates = calc.series_dates(start, end, calc.MONTH)
        assert all(d == calc.month_end(d) for d in dates[:-1])
        # no month end inside the range is missing
        expected = {calc.month_end(date(y, m, 1)) for y in range(start.year, end.year + 1) for m in range(1, 13)}
        assert {d for d in expected if start <= d <= end} <= set(dates)


class TestDiscrepancyProperties:
    @given(known_balances(source=ANCHOR), st.lists(calendar_dates(), min_size=1, max_size=6, unique=True), dated_flows())
    def test_closing_balances_that_follow_the_anchors_own_arithmetic_show_no_difference_and_no_gap(self, anchor_, days, flows):
        net = NetFlowIndex(flows).net
        printed = [
            KnownBalance(calc.balance_from_known(anchor_.balance, anchor_.date, d, net(*calc.flow_interval(anchor_.date, d))), d, STATEMENT_CLOSING, UUID(int=i + 1))
            for i, d in enumerate(days)
        ]
        assert calc.statement_differences(anchor_, printed, net, Decimal(0)) == []
        assert calc.period_gaps(printed, net, Decimal(0)) == []

    @given(st.lists(known_balances(source=STATEMENT_CLOSING), min_size=2, max_size=8), dated_flows())
    def test_the_period_gaps_add_up_to_the_whole_intervals_gap(self, closings, flows):
        net = NetFlowIndex(flows).net
        ordered = calc.deduplicate_by_date(closings)
        assume(len(ordered) >= 2)
        gaps = calc.period_gaps(closings, net, Decimal(0))
        whole = (ordered[-1].balance - ordered[0].balance) - net(ordered[0].date, ordered[-1].date)
        assert sum((g.gap for g in gaps), Decimal(0)) == whole

    @given(known_balances(source=ANCHOR), st.lists(known_balances(source=STATEMENT_CLOSING), min_size=1, max_size=6), dated_flows(), st.integers(min_value=0, max_value=2_000))
    def test_a_larger_tolerance_never_reports_more(self, anchor_, closings, flows, cents):
        net = NetFlowIndex(flows).net
        tight = calc.statement_differences(anchor_, closings, net, Decimal(0))
        loose = calc.statement_differences(anchor_, closings, net, Decimal(cents) / 100)
        assert {d.closing_date for d in loose} <= {d.closing_date for d in tight}
        assert all(abs(d.difference) > Decimal(cents) / 100 for d in loose)

    @given(money(), st.integers(min_value=1, max_value=10**9).map(lambda n: Decimal(n) / Decimal(10**6)))
    def test_conversion_to_sgd_is_within_half_a_cent_and_has_two_places(self, amount, rate):
        converted = calc.to_sgd(amount, rate)
        assert places(converted) == 2 and abs(converted - amount * rate) <= Decimal("0.005")


# ------------------------------------------------------------------------------------------------------- examples


class TestMonthAndDates:
    TODAY = date(2026, 10, 18)

    def test_a_past_month_resolves_to_its_last_day(self):
        assert calc.resolve_month("2026-09", self.TODAY) == date(2026, 9, 30)
        assert calc.resolve_month("2024-02", self.TODAY) == date(2024, 2, 29)
        assert calc.resolve_month("2025-02", self.TODAY) == date(2025, 2, 28)

    def test_the_current_month_resolves_to_today(self):
        assert calc.resolve_month("2026-10", self.TODAY) == self.TODAY

    def test_a_later_month_is_refused(self):
        with pytest.raises(calc.MonthInFuture) as refused:
            calc.resolve_month("2026-11", self.TODAY)
        assert refused.value.code == "month_in_future"

    @pytest.mark.parametrize("text", ["2026-13", "2026-00", "26-01", "2026-1", "abc", "2026/09", "", "1999-12", "2026-09-01"])
    def test_a_malformed_or_ancient_month_is_refused(self, text):
        with pytest.raises(calc.InvalidMonth):
            calc.parse_month(text)

    def test_a_lookup_date_must_be_between_2000_and_today(self):
        assert calc.validate_lookup_date(self.TODAY, self.TODAY) == self.TODAY
        assert calc.validate_lookup_date(date(2000, 1, 1), self.TODAY) == date(2000, 1, 1)
        with pytest.raises(calc.DateInFuture):
            calc.validate_lookup_date(self.TODAY + timedelta(days=1), self.TODAY)
        with pytest.raises(calc.DateOutOfRange):
            calc.validate_lookup_date(date(1999, 12, 31), self.TODAY)

    def test_the_default_range_is_the_twelve_months_ending_today(self):
        assert calc.default_series_range(date(2026, 10, 18)) == (date(2025, 10, 18), date(2026, 10, 18))
        assert calc.default_series_range(date(2024, 2, 29)) == (date(2023, 2, 28), date(2024, 2, 29))
        assert calc.default_series_range(date(2026, 3, 31)) == (date(2025, 3, 31), date(2026, 3, 31))

    def test_adding_months_clamps_to_the_month_end(self):
        assert calc.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
        assert calc.add_months(date(2026, 1, 31), -2) == date(2025, 11, 30)


class TestGranularityAndSeriesDates:
    def test_auto_is_daily_up_to_92_days_and_monthly_beyond(self):
        start = date(2026, 1, 1)
        assert calc.resolve_granularity(start, start + timedelta(days=92), calc.AUTO) == calc.DAY
        assert calc.resolve_granularity(start, start + timedelta(days=93), calc.AUTO) == calc.MONTH

    def test_a_forced_granularity_wins_and_an_unknown_one_is_refused(self):
        assert calc.resolve_granularity(date(2026, 1, 1), date(2026, 1, 5), calc.MONTH) == calc.MONTH
        with pytest.raises(calc.InvalidDateRange):
            calc.resolve_granularity(date(2026, 1, 1), date(2026, 1, 5), "weekly")

    def test_month_mode_stops_at_the_range_end_when_it_is_mid_month(self):
        assert calc.series_dates(date(2026, 1, 10), date(2026, 4, 15), calc.MONTH) == [
            date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 15),
        ]  # fmt: skip

    def test_month_mode_does_not_repeat_a_range_end_that_is_a_month_end(self):
        assert calc.series_dates(date(2026, 1, 31), date(2026, 3, 31), calc.MONTH) == [
            date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31),
        ]  # fmt: skip

    def test_a_range_inside_one_month_plots_just_its_end(self):
        assert calc.series_dates(date(2026, 5, 3), date(2026, 5, 9), calc.MONTH) == [date(2026, 5, 9)]

    def test_leap_february_is_a_month_end(self):
        assert date(2024, 2, 29) in calc.series_dates(date(2024, 1, 1), date(2024, 3, 15), calc.MONTH)

    def test_range_rules(self):
        today = date(2026, 10, 18)
        with pytest.raises(calc.InvalidDateRange):
            calc.validate_series_range(date(2026, 5, 2), date(2026, 5, 1), today, calc.DAY)
        with pytest.raises(calc.InvalidDateRange):
            calc.validate_series_range(date(2026, 5, 1), today + timedelta(days=1), today, calc.DAY)
        with pytest.raises(calc.DateOutOfRange):
            calc.validate_series_range(date(1999, 1, 1), date(2000, 6, 1), today, calc.MONTH)

    def test_a_daily_range_over_1500_points_is_refused_and_1500_is_allowed(self):
        today = date(2026, 10, 18)
        end = today
        assert len(calc.validate_series_range(end - timedelta(days=1499), end, today, calc.DAY)) == 1500
        with pytest.raises(calc.RangeTooLarge) as refused:
            calc.validate_series_range(end - timedelta(days=1500), end, today, calc.DAY)
        assert refused.value.code == "range_too_large"


class TestKnownBalanceRules:
    def test_a_known_date_is_its_own_nearest_known_balance(self):
        a, c = anchor("100.00", date(2026, 6, 30)), closing("90.00", date(2026, 3, 31))
        assert calc.choose_reference([a, c], date(2026, 3, 31)) == c

    def test_two_printed_balances_on_one_date_keep_the_one_recorded_last(self):
        first, second = closing("10.00", date(2026, 3, 31), n=1, order=1), closing("12.00", date(2026, 3, 31), n=2, order=2)
        assert calc.deduplicate_by_date([first, second]) == [second]
        assert calc.deduplicate_by_date([second, first]) == [second]

    def test_an_anchor_and_a_printed_balance_on_one_date_keep_the_anchor(self):
        a = anchor("100.00", date(2026, 3, 31))
        assert calc.deduplicate_by_date([closing("55.00", date(2026, 3, 31), order=99), a]) == [a]

    def test_nothing_known_is_an_error(self):
        with pytest.raises(ValueError):
            calc.choose_reference([], date(2026, 1, 1))

    def test_forward_adds_the_net_and_backward_subtracts_it(self):
        assert calc.balance_from_known(Decimal("100.00"), date(2026, 6, 30), date(2026, 7, 5), Decimal("-30.00")) == Decimal("70.00")
        assert calc.balance_from_known(Decimal("100.00"), date(2026, 6, 30), date(2026, 6, 25), Decimal("-30.00")) == Decimal("130.00")

    def test_the_interval_is_after_the_earlier_date_up_to_and_including_the_later(self):
        flows = {date(2026, 6, 30): Decimal("5.00"), date(2026, 7, 1): Decimal("-20.00"), date(2026, 7, 2): Decimal("3.00")}
        index = NetFlowIndex(flows)
        assert calc.flow_interval(date(2026, 6, 30), date(2026, 7, 1)) == (date(2026, 6, 30), date(2026, 7, 1))
        assert index.net(date(2026, 6, 30), date(2026, 7, 1)) == Decimal("-20.00")  # 30 June is out, 1 July is in
        assert calc.flow_interval(date(2026, 7, 2), date(2026, 6, 30)) == (date(2026, 6, 30), date(2026, 7, 2))

    def test_the_index_of_nothing_is_zero(self):
        assert NetFlowIndex({}).net(date(2026, 1, 1), date(2026, 12, 31)) == 0


class TestConversionRounding:
    @pytest.mark.parametrize(
        ("amount", "rate", "expected"),
        [
            ("100.00", "1.34", "134.00"),
            ("0.01", "0.5", "0.01"),  # 0.005 rounds up, half-up
            ("0.03", "0.5", "0.02"),  # 0.015 rounds up
            ("2.675", "1", "2.68"),
            ("-0.01", "0.5", "-0.01"),  # half-up is away from zero for negatives
            ("1000.00", "0.0123456", "12.35"),
        ],
    )
    def test_half_up_to_two_places(self, amount, rate, expected):
        assert calc.to_sgd(Decimal(amount), Decimal(rate)) == Decimal(expected)


class TestDiscrepancyExamples:
    def test_a_statement_difference_is_printed_minus_computed_from_the_anchor_alone(self):
        flows = NetFlowIndex({date(2026, 6, 15): Decimal("-40.00")})
        found = calc.statement_differences(anchor("100.00", date(2026, 6, 30)), [closing("70.00", date(2026, 6, 10))], flows.net, Decimal(0))
        # backward from the anchor: 100.00 - (-40.00) = 140.00 at 10 June; printed 70.00; difference -70.00
        assert [(d.computed_balance, d.difference) for d in found] == [(Decimal("140.00"), Decimal("-70.00"))]

    def test_a_difference_equal_to_the_tolerance_is_not_reported(self):
        flows = NetFlowIndex({})
        found = calc.statement_differences(anchor("100.00"), [closing("100.50", date(2026, 7, 31))], flows.net, Decimal("0.50"))
        assert found == []
        assert len(calc.statement_differences(anchor("100.00"), [closing("100.51", date(2026, 7, 31))], flows.net, Decimal("0.50"))) == 1

    def test_a_period_gap_points_at_the_interval_with_missing_transactions(self):
        # printed balances fall 1000 -> 800 -> 500, but only 200 was recorded in the first interval and 300 in the second
        flows = NetFlowIndex({date(2026, 2, 10): Decimal("-200.00"), date(2026, 3, 10): Decimal("-300.00")})
        closings = [closing("1000.00", date(2026, 1, 31), 1), closing("800.00", date(2026, 2, 28), 2), closing("500.00", date(2026, 3, 31), 3)]
        assert calc.period_gaps(closings, flows.net, Decimal(0)) == []
        flows_missing = NetFlowIndex({date(2026, 3, 10): Decimal("-300.00")})  # February's 200 never ingested
        gaps = calc.period_gaps(closings, flows_missing.net, Decimal(0))
        assert [(g.from_date, g.to_date, g.gap) for g in gaps] == [(date(2026, 1, 31), date(2026, 2, 28), Decimal("-200.00"))]

    def test_one_closing_balance_has_no_period(self):
        assert calc.period_gaps([closing("10.00", date(2026, 1, 31))], NetFlowIndex({}).net, Decimal(0)) == []
