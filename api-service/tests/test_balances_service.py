"""Balance business rules (AR-55 to AR-62) against a real PostgreSQL. The expected figures are worked out by hand in
each test's comments, independently of the code under test."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from account_helpers import (
    account_with_history,
    make_account,
    make_fx_rate,
    make_section,
    make_tx,
    make_unlinked_tx,
    set_anchor,
)
from transactagent_db.models import AccountType

from api_service.balances import service
from api_service.config import settings
from api_service.errors import (
    DateInFutureError,
    DateOrMonthRequiredError,
    InvalidDateRangeError,
    MonthInFutureError,
    RangeTooLargeError,
)

TODAY = date(2026, 10, 18)


def lookup(db, on_date=None, month=None, today=TODAY):
    return service.get_balances(db, on_date=on_date, month=month, today=today)


def by_name(response):
    return {a.name: a for a in response.accounts}


def main_account(db):
    """anchor 1000.00 at 30 Jun 2026. Flows: 10 Jun -100.00, 30 Jun +25.00 (already in the anchor), 5 Jul +50.00,
    20 Jul -20.00."""
    return account_with_history(
        db, "Main", anchor=("1000.00", date(2026, 6, 30)),
        flows=[(date(2026, 6, 10), "-100.00"), (date(2026, 6, 30), "25.00"), (date(2026, 7, 5), "50.00"), (date(2026, 7, 20), "-20.00")],
    )  # fmt: skip


class TestLookup:
    def test_the_balance_on_the_anchor_date_is_the_anchor(self, db_session):
        main_account(db_session)
        assert by_name(lookup(db_session, date(2026, 6, 30)))["Main"].balance_sgd == Decimal("1000.00")

    @pytest.mark.parametrize(
        ("day", "expected"),
        [
            (date(2026, 7, 4), "1000.00"),    # nothing after the anchor yet
            (date(2026, 7, 5), "1050.00"),    # + 50.00
            (date(2026, 7, 20), "1030.00"),   # + 50.00 - 20.00
            (date(2026, 8, 31), "1030.00"),   # no later flows
            (date(2026, 6, 29), "1000.00"),   # backward: nothing between 29 and 30 Jun except the +25 on the 30th? see below
            (date(2026, 6, 10), "975.00"),    # end of 10 Jun: 1000 - flows after it up to 30 Jun (+25) = 975
            (date(2026, 6, 9), "1075.00"),    # 1000 - (-100 + 25) = 1075
        ],
    )  # fmt: skip
    def test_forward_and_backward_from_the_anchor(self, db_session, day, expected):
        main_account(db_session)
        if day == date(2026, 6, 29):
            expected = "975.00"  # flows after 29 Jun up to 30 Jun = +25, so 1000 - 25
        assert by_name(lookup(db_session, day))["Main"].balance_sgd == Decimal(expected)

    def test_a_month_resolves_to_its_last_day_and_the_current_month_to_today(self, db_session):
        main_account(db_session)
        assert lookup(db_session, month="2026-07").resolved_date == date(2026, 7, 31)
        assert by_name(lookup(db_session, month="2026-07"))["Main"].balance_sgd == Decimal("1030.00")
        current = lookup(db_session, month="2026-10")
        assert (current.resolved_date, current.requested_month) == (TODAY, "2026-10")

    def test_exactly_one_of_a_date_or_a_month_is_required(self, db_session):
        for kwargs in ({}, {"on_date": date(2026, 7, 1), "month": "2026-07"}):
            with pytest.raises(DateOrMonthRequiredError):
                lookup(db_session, **kwargs)
        with pytest.raises(DateOrMonthRequiredError):
            lookup(db_session, month="July")

    def test_a_date_or_month_in_the_future_is_refused(self, db_session):
        with pytest.raises(DateInFutureError):
            lookup(db_session, date(2026, 10, 19))
        with pytest.raises(MonthInFutureError):
            lookup(db_session, month="2026-11")

    def test_an_account_without_an_anchor_is_listed_as_anchor_required_and_left_out_of_the_total(self, db_session):
        main_account(db_session)
        account_with_history(db_session, "Fresh", identifier="9", flows=[(date(2026, 7, 1), "5.00")])
        result = lookup(db_session, date(2026, 7, 20))
        fresh = by_name(result)["Fresh"]
        assert (fresh.status, fresh.balance_native, fresh.balance_sgd, fresh.basis) == ("anchor_required", None, None, None)
        assert [(e.name, e.reason) for e in result.excluded] == [("Fresh", "anchor_required")]
        assert result.combined_total_sgd == Decimal("1030.00") and result.combined_includes_count == 1

    def test_printed_closing_balances_alone_never_switch_an_account_on(self, db_session):
        account = make_account(db_session, name="OnlyClosings")
        make_section(db_session, account, closing="500.00", closing_date=date(2026, 5, 31))
        assert by_name(lookup(db_session, date(2026, 6, 1)))["OnlyClosings"].status == "anchor_required"

    def test_the_combined_total_is_the_sum_of_the_rows_shown(self, db_session):
        main_account(db_session)
        account_with_history(db_session, "Second", identifier="2", anchor=("20.50", date(2026, 7, 1)))
        result = lookup(db_session, date(2026, 7, 20))
        assert result.combined_total_sgd == sum((a.balance_sgd for a in result.accounts if a.status == "ok"), Decimal(0)) == Decimal("1050.50")

    def test_no_deposit_accounts_is_an_empty_result_not_an_error(self, db_session):
        make_account(db_session, name="Card", account_type=AccountType.CREDIT_CARD)
        result = lookup(db_session, date(2026, 7, 1))
        assert (result.accounts, result.combined_total_sgd, result.excluded, result.combined_includes_count) == ([], None, [], 0)

    def test_credit_card_and_unknown_accounts_never_appear_even_with_an_anchor_row(self, db_session):
        card = make_account(db_session, name="Card", account_type=AccountType.CREDIT_CARD, identifier="1")
        set_anchor(db_session, card, "10.00", date(2026, 1, 1))
        make_account(db_session, name="Mystery", account_type=AccountType.UNKNOWN, identifier="2")
        assert lookup(db_session, date(2026, 7, 1)).accounts == []

    def test_the_ingested_through_date_is_the_latest_transaction_of_all_including_unlinked_ones(self, db_session):
        main_account(db_session)
        make_unlinked_tx(db_session, date(2026, 9, 1), "1.00")
        result = lookup(db_session, date(2026, 7, 20))
        assert result.ingested_through_date == date(2026, 9, 1)
        assert by_name(result)["Main"].latest_transaction_date == date(2026, 7, 20)  # the account's own

    def test_transactions_linked_to_no_account_are_reported_not_counted(self, db_session):
        main_account(db_session)
        make_unlinked_tx(db_session, date(2026, 7, 31), "100.00", bank="GXS Bank")
        make_unlinked_tx(db_session, date(2026, 7, 1), "-30.00", bank="GXS Bank")
        result = lookup(db_session, date(2026, 8, 31))
        notice = result.unlinked_transactions
        assert (notice.count, notice.bank_names, notice.earliest_date, notice.latest_date) == (2, ["GXS Bank"], date(2026, 7, 1), date(2026, 7, 31))
        assert [(n.currency, n.net) for n in notice.net_by_currency] == [("SGD", Decimal("70.00"))]
        assert by_name(result)["Main"].balance_sgd == Decimal("1030.00")  # unaffected

    def test_there_is_no_notice_when_every_transaction_is_linked(self, db_session):
        main_account(db_session)
        assert lookup(db_session, date(2026, 7, 20)).unlinked_transactions is None


class TestNearestKnownBalance:
    def account(self, db):
        """anchor 500.00 at 30 Jun; a printed closing balance of 300.00 at 31 Mar; flows 15 Apr -10.00, 10 May +60.00."""
        account = make_account(db, name="Nearest", identifier="n")
        set_anchor(db, account, "500.00", date(2026, 6, 30))
        section = make_section(db, account, closing="300.00", closing_date=date(2026, 3, 31))
        make_tx(db, section, date(2026, 4, 15), "-10.00")
        make_tx(db, section, date(2026, 5, 10), "60.00")
        return account

    def at(self, db, day):
        return by_name(lookup(db, day))["Nearest"]

    def test_on_a_statements_closing_date_the_balance_is_the_statement(self, db_session):
        self.account(db_session)
        result = self.at(db_session, date(2026, 3, 31))
        assert result.balance_sgd == Decimal("300.00")
        assert (result.basis.source, result.basis.date) == ("statement_closing", date(2026, 3, 31))

    def test_a_date_nearer_the_statement_is_worked_from_the_statement(self, db_session):
        self.account(db_session)
        assert self.at(db_session, date(2026, 4, 5)).balance_sgd == Decimal("300.00")  # 300 + flows in (31 Mar, 5 Apr] = 300
        assert self.at(db_session, date(2026, 5, 10)).balance_sgd == Decimal("350.00")  # 300 - 10 + 60

    def test_a_date_nearer_the_anchor_is_worked_from_the_anchor(self, db_session):
        self.account(db_session)
        result = self.at(db_session, date(2026, 5, 20))  # 50 days from the statement, 41 from the anchor
        assert result.balance_sgd == Decimal("500.00") and result.basis.source == "anchor"

    def test_a_tie_goes_to_the_anchor(self, db_session):
        account = make_account(db_session, name="Tie")
        set_anchor(db_session, account, "100.00", date(2026, 6, 30))
        make_section(db_session, account, closing="999.00", closing_date=date(2026, 6, 20))
        result = by_name(lookup(db_session, date(2026, 6, 25)))["Tie"]  # five days from each
        assert (result.balance_sgd, result.basis.source) == (Decimal("100.00"), "anchor")


class TestForeignCurrency:
    def usd(self, db, anchor="100.00"):
        return account_with_history(db, "USD savings", identifier="u", currency="USD", anchor=(anchor, date(2026, 6, 30)))

    def test_an_exact_rate_converts_without_a_warning(self, db_session):
        self.usd(db_session)
        make_fx_rate(db_session, "USD", date(2026, 6, 30), "1.30")
        result = by_name(lookup(db_session, date(2026, 6, 30)))["USD savings"]
        assert (result.balance_native, result.balance_sgd, result.is_approximate, result.fx_rate_date) == (Decimal("100.00"), Decimal("130.00"), False, date(2026, 6, 30))

    def test_an_earlier_rate_converts_and_is_marked_approximate(self, db_session):
        self.usd(db_session)
        make_fx_rate(db_session, "USD", date(2026, 6, 30), "1.30")
        result = lookup(db_session, date(2026, 7, 10))
        usd = by_name(result)["USD savings"]
        assert (usd.balance_sgd, usd.is_approximate, usd.fx_rate_date) == (Decimal("130.00"), True, date(2026, 6, 30))
        assert result.has_approximate is True

    def test_with_no_rate_on_or_before_the_date_the_account_is_unavailable_and_excluded(self, db_session):
        self.usd(db_session)
        main_account(db_session)
        make_fx_rate(db_session, "USD", date(2026, 8, 1), "1.30")  # only a LATER rate exists
        result = lookup(db_session, date(2026, 7, 20))
        usd = by_name(result)["USD savings"]
        assert (usd.status, usd.balance_sgd, usd.balance_native) == ("fx_unavailable", None, Decimal("100.00"))
        assert [(e.name, e.reason) for e in result.excluded] == [("USD savings", "fx_unavailable")]
        assert result.combined_total_sgd == Decimal("1030.00") and result.combined_includes_count == 1

    def test_the_conversion_rounds_half_up(self, db_session):
        self.usd(db_session, anchor="10.01")
        make_fx_rate(db_session, "USD", date(2026, 6, 30), "0.50")
        assert by_name(lookup(db_session, date(2026, 6, 30)))["USD savings"].balance_sgd == Decimal("5.01")  # 5.005 half-up


class TestSeries:
    def build(self, db):
        main_account(db)
        TestNearestKnownBalance().account(db)
        account_with_history(db, "USD savings", identifier="u", currency="USD", anchor=("100.00", date(2026, 6, 30)), flows=[(date(2026, 7, 3), "10.00")])
        make_fx_rate(db, "USD", date(2026, 6, 30), "1.30")

    def series(self, db, **kwargs):
        return service.get_series(db, today=TODAY, **kwargs)

    @pytest.mark.parametrize("granularity", ["day", "month"])
    def test_every_plotted_point_equals_the_single_date_lookup_for_every_account(self, db_session, granularity):
        self.build(db_session)
        result = self.series(db_session, start=date(2026, 3, 20), end=date(2026, 8, 20), granularity=granularity)
        assert result.granularity == granularity and len(result.points) > 4
        for point in result.points:
            looked_up = lookup(db_session, point.date)
            by_id = {str(a.account_id): a.balance_sgd for a in looked_up.accounts}
            assert point.per_account == {k: by_id[k] for k in point.per_account}
            assert point.combined_sgd == looked_up.combined_total_sgd

    def test_the_default_range_is_the_last_twelve_months_in_month_points_ending_today(self, db_session):
        self.build(db_session)
        result = self.series(db_session)
        assert (result.start, result.end, result.granularity) == (date(2025, 10, 18), TODAY, "month")
        assert result.points[0].date == date(2025, 10, 31) and result.points[-1].date == TODAY
        assert [p.date.day for p in result.points[:-1]] == [31, 30, 31, 31, 28, 31, 30, 31, 30, 31, 31, 30]  # Oct 2025 .. Sep 2026

    def test_auto_is_daily_for_a_short_range(self, db_session):
        self.build(db_session)
        result = self.series(db_session, start=date(2026, 7, 1), end=date(2026, 7, 10))
        assert result.granularity == "day" and len(result.points) == 10

    def test_a_date_with_no_usable_rate_is_a_gap_for_that_account_and_left_out_of_the_total(self, db_session):
        self.build(db_session)
        result = self.series(db_session, start=date(2026, 6, 28), end=date(2026, 7, 1), granularity="day")
        usd_id = next(str(a.account_id) for a in result.accounts if a.name == "USD savings")
        first = result.points[0]  # 28 Jun: the only rate is dated 30 Jun, so there is none on or before the 28th
        assert first.per_account[usd_id] is None
        others = sum((v for k, v in first.per_account.items() if k != usd_id and v is not None), Decimal(0))
        assert first.combined_sgd == others
        assert result.points[2].per_account[usd_id] == Decimal("130.00")  # 30 Jun: rate on the day

    def test_accounts_without_an_anchor_are_listed_once_as_missing_and_not_plotted(self, db_session):
        self.build(db_session)
        account_with_history(db_session, "Fresh", identifier="f")
        result = self.series(db_session, start=date(2026, 7, 1), end=date(2026, 7, 3), granularity="day")
        assert [(m.name, m.reason) for m in result.missing_accounts] == [("Fresh", "anchor_required")]
        assert "Fresh" not in {a.name for a in result.accounts}

    def test_with_nothing_to_plot_there_are_no_points(self, db_session):
        account_with_history(db_session, "Fresh", identifier="f")
        result = self.series(db_session)
        assert result.points == [] and result.accounts == [] and len(result.missing_accounts) == 1

    def test_range_errors(self, db_session):
        with pytest.raises(InvalidDateRangeError):
            self.series(db_session, start=date(2026, 5, 2), end=date(2026, 5, 1))
        with pytest.raises(InvalidDateRangeError):
            self.series(db_session, start=date(2026, 5, 1), end=date(2026, 10, 19))
        with pytest.raises(RangeTooLargeError):
            self.series(db_session, start=date(2022, 1, 1), end=date(2026, 10, 18), granularity="day")
        with pytest.raises(InvalidDateRangeError):
            self.series(db_session, granularity="weekly")


class TestDiscrepancies:
    def test_agreeing_balances_report_nothing(self, db_session):
        account = make_account(db_session, name="Agrees")
        set_anchor(db_session, account, "500.00", date(2026, 3, 31))
        section = make_section(db_session, account, closing="800.00", closing_date=date(2026, 2, 28))
        make_tx(db_session, section, date(2026, 3, 10), "-300.00")  # 500 - (-300) = 800 at 28 Feb: agrees
        result = service.get_discrepancies(db_session)
        assert result.items == [] and result.accounts_checked == 1

    def test_a_statement_difference_is_printed_minus_computed_from_the_anchor_alone(self, db_session):
        TestNearestKnownBalance().account(db_session)
        # anchor 500 at 30 Jun, flows after 31 Mar: -10 + 60 = +50, so computed at 31 Mar = 500 - 50 = 450; printed 300
        [item] = service.get_discrepancies(db_session).items
        [difference] = item.statement_differences
        assert (difference.computed_balance, difference.printed_balance, difference.difference) == (Decimal("450.00"), Decimal("300.00"), Decimal("-150.00"))
        assert item.period_gaps == [] and (item.statements_checked, item.periods_checked) == (1, 0)

    def test_a_period_gap_marks_the_interval_whose_transactions_are_missing(self, db_session):
        account = make_account(db_session, name="Gappy")
        set_anchor(db_session, account, "500.00", date(2026, 3, 31))
        section = make_section(db_session, account, closing="1000.00", closing_date=date(2026, 1, 31))
        make_section(db_session, account, closing="800.00", closing_date=date(2026, 2, 28))
        make_section(db_session, account, closing="500.00", closing_date=date(2026, 3, 31))
        make_tx(db_session, section, date(2026, 3, 10), "-300.00")  # March is complete; February's -200 was never ingested
        [item] = service.get_discrepancies(db_session).items
        assert [(g.from_date, g.to_date, g.gap) for g in item.period_gaps] == [(date(2026, 1, 31), date(2026, 2, 28), Decimal("-200.00"))]
        # cumulative view: computed at 31 Jan = 500 - (-300) = 800 against printed 1000, difference +200; 28 Feb agrees
        assert [(d.closing_date, d.difference) for d in item.statement_differences] == [(date(2026, 1, 31), Decimal("200.00"))]

    def test_correcting_a_wrong_anchor_removes_the_difference_it_caused_but_not_the_one_from_missing_transactions(self, db_session):
        from api_service.accounts.schemas import AnchorRequest
        from api_service.accounts.service import set_anchor as replace_anchor

        account = make_account(db_session, name="WrongAnchor")
        make_section(db_session, account, closing="1000.00", closing_date=date(2026, 1, 31))
        make_section(db_session, account, closing="900.00", closing_date=date(2026, 2, 28))  # fell 100; no transaction recorded
        set_anchor(db_session, account, "1100.00", date(2026, 3, 31))  # wrong: with nothing after 28 Feb it should be 900.00

        before = service.get_discrepancies(db_session).items[0]
        # computed from the anchor alone is 1100.00 on both dates: 1000 - 1100 = -100 and 900 - 1100 = -200
        assert [(d.closing_date, d.difference) for d in before.statement_differences] == [
            (date(2026, 1, 31), Decimal("-100.00")),
            (date(2026, 2, 28), Decimal("-200.00")),
        ]

        replace_anchor(db_session, account.id, AnchorRequest(balance="900.00", as_of_date=date(2026, 3, 31)), TODAY)

        after = service.get_discrepancies(db_session).items[0]
        # 28 Feb now agrees (900 vs 900); 31 Jan still differs (printed 1000, computed 900) because the 100 that left in
        # February was never ingested, and the period gap that marks it does not depend on the anchor
        assert [(d.closing_date, d.difference) for d in after.statement_differences] == [(date(2026, 1, 31), Decimal("100.00"))]
        assert [(g.from_date, g.to_date, g.gap) for g in after.period_gaps] == [(date(2026, 1, 31), date(2026, 2, 28), Decimal("-100.00"))]

    def test_an_account_without_an_anchor_is_not_checked_at_all(self, db_session):
        account = make_account(db_session, name="NoAnchor")
        make_section(db_session, account, closing="1000.00", closing_date=date(2026, 1, 31))
        make_section(db_session, account, closing="1.00", closing_date=date(2026, 2, 28))
        result = service.get_discrepancies(db_session)
        assert result.items == [] and result.accounts_checked == 0

    def test_the_tolerance_setting_decides_what_counts(self, db_session, monkeypatch):
        TestNearestKnownBalance().account(db_session)  # the difference is exactly -150.00
        monkeypatch.setattr(settings, "balance_mismatch_tolerance", Decimal("150.00"))
        assert service.get_discrepancies(db_session).items == []  # equal to the tolerance: not reported
        monkeypatch.setattr(settings, "balance_mismatch_tolerance", Decimal("149.99"))
        result = service.get_discrepancies(db_session)
        assert len(result.items) == 1 and result.tolerance == Decimal("149.99")


class TestToday:
    NOW = datetime(2026, 10, 17, 23, 30, tzinfo=UTC)  # 07:30 on the 18th in Singapore

    def test_today_follows_the_reporting_time_zone_setting(self, monkeypatch):
        assert service.today_in_reporting_zone(self.NOW) == date(2026, 10, 18)  # the default, Asia/Singapore
        monkeypatch.setattr(settings, "reporting_time_zone", "UTC")
        assert service.today_in_reporting_zone(self.NOW) == date(2026, 10, 17)
        monkeypatch.setattr(settings, "reporting_time_zone", "America/Los_Angeles")
        assert service.today_in_reporting_zone(self.NOW) == date(2026, 10, 17)
