"""Tests for recurring_payments/cycle.py. Deliberately mirrors
ingestion-worker/tests/test_recurring_payments_cycle.py's cases for the functions
shared in spirit between the two services (kept behavior-identical, though not
code-identical -- see cycle.py's module docstring) plus this service's own
status-only additions (latest_instance_on_or_before, next_instance_after).
"""

from datetime import date

from transactagent_db.models import RecurringPaymentFrequency

from api_service.recurring_payments.cycle import (
    cycle_period_for,
    latest_instance_on_or_before,
    nearest_annual_due_date_instance,
    nearest_monthly_due_date_instance,
    next_instance_after,
)


class TestNearestMonthlyDueDateInstance:
    def test_transaction_on_due_day_matches_same_month_exactly(self):
        assert nearest_monthly_due_date_instance(due_day=15, transaction_date=date(2026, 6, 15)) == date(2026, 6, 15)

    def test_transaction_just_after_month_start_is_closer_to_next_months_due_date(self):
        assert nearest_monthly_due_date_instance(due_day=1, transaction_date=date(2026, 1, 30)) == date(2026, 2, 1)

    def test_clamps_to_last_day_of_a_short_month(self):
        assert nearest_monthly_due_date_instance(due_day=31, transaction_date=date(2026, 2, 15)) == date(2026, 2, 28)


class TestNearestAnnualDueDateInstance:
    def test_transaction_on_due_date_matches_same_year_exactly(self):
        result = nearest_annual_due_date_instance(due_month=8, due_day=21, transaction_date=date(2026, 8, 21))
        assert result == date(2026, 8, 21)


class TestCyclePeriodFor:
    def test_monthly_format(self):
        assert cycle_period_for(RecurringPaymentFrequency.MONTHLY, date(2026, 8, 21)) == "2026-08"

    def test_annual_format(self):
        assert cycle_period_for(RecurringPaymentFrequency.ANNUAL, date(2026, 8, 21)) == "2026"


class TestLatestInstanceOnOrBefore:
    """AR-15 status computation -- always returns a past-or-today instance, never
    a future one, unlike nearest_*_due_date_instance."""

    def test_due_date_already_passed_this_month(self):
        result = latest_instance_on_or_before(RecurringPaymentFrequency.MONTHLY, None, due_day=5, reference_date=date(2026, 8, 20))
        assert result == date(2026, 8, 5)

    def test_due_date_not_yet_reached_this_month_falls_back_to_last_month(self):
        result = latest_instance_on_or_before(RecurringPaymentFrequency.MONTHLY, None, due_day=28, reference_date=date(2026, 8, 5))
        assert result == date(2026, 7, 28)

    def test_due_date_is_exactly_today(self):
        result = latest_instance_on_or_before(RecurringPaymentFrequency.MONTHLY, None, due_day=15, reference_date=date(2026, 8, 15))
        assert result == date(2026, 8, 15)

    def test_january_falls_back_to_previous_december(self):
        result = latest_instance_on_or_before(RecurringPaymentFrequency.MONTHLY, None, due_day=28, reference_date=date(2026, 1, 5))
        assert result == date(2025, 12, 28)

    def test_annual_payment_due_date_already_passed_this_year(self):
        result = latest_instance_on_or_before(
            RecurringPaymentFrequency.ANNUAL, due_month=8, due_day=21, reference_date=date(2026, 9, 1)
        )
        assert result == date(2026, 8, 21)

    def test_annual_payment_due_date_not_yet_reached_this_year(self):
        result = latest_instance_on_or_before(
            RecurringPaymentFrequency.ANNUAL, due_month=8, due_day=21, reference_date=date(2026, 3, 1)
        )
        assert result == date(2025, 8, 21)


class TestNextInstanceAfter:
    def test_monthly_next_instance_is_one_month_later(self):
        result = next_instance_after(RecurringPaymentFrequency.MONTHLY, None, due_day=15, instance=date(2026, 8, 15))
        assert result == date(2026, 9, 15)

    def test_monthly_next_instance_across_year_boundary(self):
        result = next_instance_after(RecurringPaymentFrequency.MONTHLY, None, due_day=15, instance=date(2026, 12, 15))
        assert result == date(2027, 1, 15)

    def test_annual_next_instance_is_one_year_later(self):
        result = next_instance_after(RecurringPaymentFrequency.ANNUAL, due_month=8, due_day=21, instance=date(2026, 8, 21))
        assert result == date(2027, 8, 21)
