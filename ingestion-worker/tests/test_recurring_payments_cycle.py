"""Tests for recurring_payments/cycle.py's pure date-math (WR-17)."""

from datetime import date

from ingestion_worker.recurring_payments.cycle import (
    cycle_period_for,
    nearest_annual_due_date_instance,
    nearest_due_date_instance,
    nearest_monthly_due_date_instance,
)
from transactagent_db.models import RecurringPaymentFrequency


class TestNearestMonthlyDueDateInstance:
    def test_transaction_on_due_day_matches_same_month_exactly(self):
        result = nearest_monthly_due_date_instance(due_day=15, transaction_date=date(2026, 6, 15))
        assert result == date(2026, 6, 15)

    def test_transaction_just_after_month_start_is_closer_to_next_months_due_date(self):
        # due on the 1st; a transaction on the 30th is 2 days from next month's 1st
        # but 29 days from this month's 1st.
        result = nearest_monthly_due_date_instance(due_day=1, transaction_date=date(2026, 1, 30))
        assert result == date(2026, 2, 1)

    def test_transaction_early_in_month_is_closer_to_same_months_due_date(self):
        result = nearest_monthly_due_date_instance(due_day=1, transaction_date=date(2026, 1, 3))
        assert result == date(2026, 1, 1)

    def test_transaction_just_before_month_end_due_date_is_closer_to_previous_months(self):
        # due on the 28th; a transaction on Mar 2 is 2 days from Feb 28 but 26 days
        # from Mar 28.
        result = nearest_monthly_due_date_instance(due_day=28, transaction_date=date(2026, 3, 2))
        assert result == date(2026, 2, 28)

    def test_clamps_to_last_day_of_a_short_month(self):
        # 2026 is not a leap year -- Feb has 28 days. due_day=31 clamps to Feb 28.
        result = nearest_monthly_due_date_instance(due_day=31, transaction_date=date(2026, 2, 15))
        assert result == date(2026, 2, 28)

    def test_december_to_january_year_boundary(self):
        result = nearest_monthly_due_date_instance(due_day=1, transaction_date=date(2026, 12, 30))
        assert result == date(2027, 1, 1)


class TestNearestAnnualDueDateInstance:
    def test_transaction_on_due_date_matches_same_year_exactly(self):
        result = nearest_annual_due_date_instance(due_month=8, due_day=21, transaction_date=date(2026, 8, 21))
        assert result == date(2026, 8, 21)

    def test_transaction_just_before_due_date_matches_same_year(self):
        result = nearest_annual_due_date_instance(due_month=8, due_day=21, transaction_date=date(2026, 8, 20))
        assert result == date(2026, 8, 21)

    def test_transaction_in_late_december_is_closer_to_next_years_january_due_date(self):
        result = nearest_annual_due_date_instance(due_month=1, due_day=5, transaction_date=date(2026, 12, 30))
        assert result == date(2027, 1, 5)


class TestNearestDueDateInstanceDispatch:
    def test_monthly_frequency_dispatches_to_monthly_logic(self):
        result = nearest_due_date_instance(
            RecurringPaymentFrequency.MONTHLY, due_month=None, due_day=15, transaction_date=date(2026, 6, 15)
        )
        assert result == date(2026, 6, 15)

    def test_annual_frequency_dispatches_to_annual_logic(self):
        result = nearest_due_date_instance(
            RecurringPaymentFrequency.ANNUAL, due_month=8, due_day=21, transaction_date=date(2026, 8, 21)
        )
        assert result == date(2026, 8, 21)


class TestCyclePeriodFor:
    def test_monthly_format(self):
        assert cycle_period_for(RecurringPaymentFrequency.MONTHLY, date(2026, 8, 21)) == "2026-08"

    def test_annual_format(self):
        assert cycle_period_for(RecurringPaymentFrequency.ANNUAL, date(2026, 8, 21)) == "2026"
