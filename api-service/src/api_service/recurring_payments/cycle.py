"""Pure date-math for recurring-payment cycle resolution (WR-17/AR-15).

Deliberately duplicated from ingestion_worker/recurring_payments/cycle.py, not
imported: API Service and Ingestion Worker Service are separately deployable
codebases sharing no library beyond the DB schema (component-dependency.md).
Functional Design flagged this explicitly -- keep behavior identical to the
Worker's copy (see test_recurring_payments_cycle.py, mirrored test cases on both
sides), since the Dashboard's idea of "this cycle" must match what the Worker
actually matched against.
"""

import calendar
from datetime import date

from transactagent_db.models import RecurringPaymentFrequency


def _last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _month_instance(year: int, month: int, due_day: int) -> date:
    day = min(due_day, _last_day_of_month(year, month))
    return date(year, month, day)


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    total = (year * 12 + (month - 1)) + delta
    return total // 12, total % 12 + 1


def nearest_monthly_due_date_instance(due_day: int, transaction_date: date) -> date:
    same_month = _month_instance(transaction_date.year, transaction_date.month, due_day)
    if transaction_date.day < due_day:
        adj_year, adj_month = _add_months(transaction_date.year, transaction_date.month, -1)
    else:
        adj_year, adj_month = _add_months(transaction_date.year, transaction_date.month, 1)
    adjacent = _month_instance(adj_year, adj_month, due_day)

    return same_month if abs((transaction_date - same_month).days) <= abs((transaction_date - adjacent).days) else adjacent


def nearest_annual_due_date_instance(due_month: int, due_day: int, transaction_date: date) -> date:
    same_year = _month_instance(transaction_date.year, due_month, due_day)
    if (transaction_date.month, transaction_date.day) < (due_month, due_day):
        adjacent = _month_instance(transaction_date.year - 1, due_month, due_day)
    else:
        adjacent = _month_instance(transaction_date.year + 1, due_month, due_day)

    return same_year if abs((transaction_date - same_year).days) <= abs((transaction_date - adjacent).days) else adjacent


def nearest_due_date_instance(
    frequency: RecurringPaymentFrequency, due_month: int | None, due_day: int, reference_date: date
) -> date:
    if frequency == RecurringPaymentFrequency.MONTHLY:
        return nearest_monthly_due_date_instance(due_day, reference_date)
    assert due_month is not None  # BR-19 guarantees this for annual payments
    return nearest_annual_due_date_instance(due_month, due_day, reference_date)


def cycle_period_for(frequency: RecurringPaymentFrequency, instance: date) -> str:
    if frequency == RecurringPaymentFrequency.MONTHLY:
        return f"{instance.year:04d}-{instance.month:02d}"
    return f"{instance.year:04d}"


def latest_instance_on_or_before(
    frequency: RecurringPaymentFrequency, due_month: int | None, due_day: int, reference_date: date
) -> date:
    """AR-15 status computation only (not used by the Worker's matching, which uses
    `nearest_due_date_instance` instead -- status needs "the cycle currently due,"
    not "whichever instance a specific transaction is closest to"). A due-date
    pattern recurs indefinitely, so a past-or-today instance always exists."""
    if frequency == RecurringPaymentFrequency.MONTHLY:
        candidate = _month_instance(reference_date.year, reference_date.month, due_day)
        if candidate <= reference_date:
            return candidate
        prev_year, prev_month = _add_months(reference_date.year, reference_date.month, -1)
        return _month_instance(prev_year, prev_month, due_day)

    assert due_month is not None  # BR-19 guarantees this for annual payments
    candidate = _month_instance(reference_date.year, due_month, due_day)
    if candidate <= reference_date:
        return candidate
    return _month_instance(reference_date.year - 1, due_month, due_day)


def next_instance_after(
    frequency: RecurringPaymentFrequency, due_month: int | None, due_day: int, instance: date
) -> date:
    """The due-date instance immediately following `instance` -- used to decide
    whether a just-paid cycle should still show as `due_soon` because the next
    one is already close (AR-15)."""
    if frequency == RecurringPaymentFrequency.MONTHLY:
        year, month = _add_months(instance.year, instance.month, 1)
        return _month_instance(year, month, due_day)

    assert due_month is not None
    return _month_instance(instance.year + 1, due_month, due_day)
