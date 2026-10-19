"""Balance data access (AR-55 to AR-62, AR-66) against a real PostgreSQL."""

from datetime import date
from decimal import Decimal

from account_helpers import (
    account_with_history,
    make_account,
    make_fx_rate,
    make_section,
    make_unlinked_tx,
    set_anchor,
)
from transactagent_db.models import AccountType

from api_service.balances import repository


class TestDepositAccounts:
    def test_only_deposit_accounts_are_returned_with_their_anchors(self, db_session):
        deposit = make_account(db_session, name="b savings", identifier="1")
        make_account(db_session, name="card", account_type=AccountType.CREDIT_CARD, identifier="2")
        make_account(db_session, name="mystery", account_type=AccountType.UNKNOWN, identifier="3")
        set_anchor(db_session, deposit, "10.00", date(2026, 1, 1))
        make_account(db_session, name="A current", identifier="4")

        rows = repository.list_deposit_accounts(db_session)

        assert [r.name for r in rows] == ["A current", "b savings"]  # case-insensitive order
        assert (rows[1].anchor_balance, rows[1].anchor_date) == (Decimal("10.00"), date(2026, 1, 1))
        assert (rows[0].anchor_balance, rows[0].anchor_date) == (None, None)


class TestClosingBalances:
    def test_only_complete_closing_balances_are_returned_in_record_order_per_account(self, db_session):
        a, b = make_account(db_session, name="a", identifier="1"), make_account(db_session, name="b", identifier="2")
        make_section(db_session, a, closing="10.00", closing_date=date(2026, 1, 31))
        make_section(db_session, a)  # no closing balance
        make_section(db_session, a, closing="20.00", closing_date=date(2026, 2, 28))
        make_section(db_session, b, closing="7.00", closing_date=date(2026, 1, 31))

        closings = repository.list_closing_balances(db_session, [a.id, b.id])

        assert [(c.balance, c.closing_date) for c in closings[a.id]] == [(Decimal("10.00"), date(2026, 1, 31)), (Decimal("20.00"), date(2026, 2, 28))]
        assert closings[a.id][0].recorded_order < closings[a.id][1].recorded_order
        assert [c.balance for c in closings[b.id]] == [Decimal("7.00")]

    def test_an_account_without_any_has_no_entry(self, db_session):
        a = make_account(db_session)
        assert repository.list_closing_balances(db_session, [a.id]) == {}


class TestNetFlow:
    def flows(self, db_session):
        return account_with_history(
            db_session,
            flows=[(date(2026, 6, 30), "5.00"), (date(2026, 7, 1), "-20.00"), (date(2026, 7, 2), "3.00"), (date(2026, 7, 9), "100.00")],
        )

    def test_the_earlier_date_is_excluded_and_the_later_included(self, db_session):
        account, _ = self.flows(db_session)
        assert repository.net_flow_between(db_session, account.id, date(2026, 6, 30), date(2026, 7, 1)) == Decimal("-20.00")
        assert repository.net_flow_between(db_session, account.id, date(2026, 6, 29), date(2026, 7, 2)) == Decimal("-12.00")

    def test_an_empty_interval_is_zero(self, db_session):
        account, _ = self.flows(db_session)
        assert repository.net_flow_between(db_session, account.id, date(2026, 8, 1), date(2026, 9, 1)) == Decimal(0)

    def test_another_accounts_and_unlinked_transactions_are_not_counted(self, db_session):
        mine, _ = self.flows(db_session)
        _other, _other_section = account_with_history(db_session, "Other", identifier="9", flows=[(date(2026, 7, 1), "1000.00")])
        make_unlinked_tx(db_session, date(2026, 7, 1), "5000.00")
        assert repository.net_flow_between(db_session, mine.id, date(2026, 6, 30), date(2026, 7, 1)) == Decimal("-20.00")

    def test_daily_totals_are_per_account_and_per_day(self, db_session):
        account, _section = account_with_history(db_session, flows=[(date(2026, 7, 1), "10.00"), (date(2026, 7, 1), "-4.00"), (date(2026, 7, 3), "1.50")])
        empty = make_account(db_session, name="empty", identifier="e")
        totals = repository.daily_flow_totals(db_session, [account.id, empty.id])
        assert totals[account.id] == {date(2026, 7, 1): Decimal("6.00"), date(2026, 7, 3): Decimal("1.50")}
        assert totals[empty.id] == {}


class TestLatestDates:
    def test_overall_includes_unlinked_transactions_but_per_account_does_not(self, db_session):
        account, _ = account_with_history(db_session, flows=[(date(2026, 3, 1), "1")])
        make_unlinked_tx(db_session, date(2026, 8, 1), "1")
        assert repository.latest_transaction_date_overall(db_session) == date(2026, 8, 1)
        assert repository.latest_transaction_dates_by_account(db_session, [account.id]) == {account.id: date(2026, 3, 1)}

    def test_no_transactions_means_none(self, db_session):
        assert repository.latest_transaction_date_overall(db_session) is None


class TestUnlinkedSummary:
    def test_none_when_every_transaction_is_linked(self, db_session):
        account_with_history(db_session, flows=[(date(2026, 3, 1), "1")])
        assert repository.unlinked_summary(db_session) is None

    def test_count_banks_dates_and_net_per_currency(self, db_session):
        make_unlinked_tx(db_session, date(2026, 7, 31), "100.00", bank="GXS Bank")
        make_unlinked_tx(db_session, date(2026, 7, 1), "-30.00", bank="GXS Bank")
        make_unlinked_tx(db_session, date(2026, 7, 15), "-5.00", bank="Trust", currency="USD")
        summary = repository.unlinked_summary(db_session)
        assert summary.count == 3 and summary.bank_names == ["GXS Bank", "Trust"]
        assert (summary.earliest_date, summary.latest_date) == (date(2026, 7, 1), date(2026, 7, 31))
        assert summary.net_by_currency == [("SGD", Decimal("70.00")), ("USD", Decimal("-5.00"))]


class TestFxRate:
    def test_the_nearest_earlier_rate_is_chosen(self, db_session):
        make_fx_rate(db_session, "USD", date(2026, 1, 1), "1.30")
        make_fx_rate(db_session, "USD", date(2026, 3, 1), "1.35")
        make_fx_rate(db_session, "USD", date(2026, 6, 1), "1.40")
        assert repository.nearest_earlier_rate(db_session, "USD", date(2026, 4, 15)) == (Decimal("1.35000000"), date(2026, 3, 1))

    def test_an_exact_date_is_used(self, db_session):
        make_fx_rate(db_session, "USD", date(2026, 3, 1), "1.35")
        assert repository.nearest_earlier_rate(db_session, "USD", date(2026, 3, 1))[1] == date(2026, 3, 1)

    def test_none_when_every_rate_is_later_or_another_currency(self, db_session):
        make_fx_rate(db_session, "USD", date(2026, 6, 1), "1.40")
        make_fx_rate(db_session, "EUR", date(2026, 1, 1), "1.50")
        assert repository.nearest_earlier_rate(db_session, "USD", date(2026, 5, 31)) is None
