"""Pure date-math for recurring-payment cycle resolution (WR-17). Deliberately
pure (no DB/I/O), same rationale as categorization/similarity.py, and a clean
target for direct unit testing.
"""

import calendar
from datetime import date

from transactagent_db.models import RecurringPaymentFrequency


def _last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _month_instance(year: int, month: int, due_day: int) -> date:
    """A due day beyond the month's actual length clamps to the last day of that
    month (e.g. due_day=31 in February lands on the 28th/29th)."""
    day = min(due_day, _last_day_of_month(year, month))
    return date(year, month, day)


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    total = (year * 12 + (month - 1)) + delta
    return total // 12, total % 12 + 1


def nearest_monthly_due_date_instance(due_day: int, transaction_date: date) -> date:
    """WR-17: of the two plausible monthly due-date instances (this calendar month,
    or the adjacent one), returns whichever is numerically closer to
    transaction_date by day distance -- resolving which cycle a transaction near a
    month boundary belongs to."""
    same_month = _month_instance(transaction_date.year, transaction_date.month, due_day)
    if transaction_date.day < due_day:
        adj_year, adj_month = _add_months(transaction_date.year, transaction_date.month, -1)
    else:
        adj_year, adj_month = _add_months(transaction_date.year, transaction_date.month, 1)
    adjacent = _month_instance(adj_year, adj_month, due_day)

    return same_month if abs((transaction_date - same_month).days) <= abs((transaction_date - adjacent).days) else adjacent


def nearest_annual_due_date_instance(due_month: int, due_day: int, transaction_date: date) -> date:
    """Same reasoning as `nearest_monthly_due_date_instance`, one level up: the two
    plausible instances are this year's and the adjacent year's."""
    same_year = _month_instance(transaction_date.year, due_month, due_day)
    if (transaction_date.month, transaction_date.day) < (due_month, due_day):
        adjacent = _month_instance(transaction_date.year - 1, due_month, due_day)
    else:
        adjacent = _month_instance(transaction_date.year + 1, due_month, due_day)

    return same_year if abs((transaction_date - same_year).days) <= abs((transaction_date - adjacent).days) else adjacent


def nearest_due_date_instance(
    frequency: RecurringPaymentFrequency, due_month: int | None, due_day: int, transaction_date: date
) -> date:
    if frequency == RecurringPaymentFrequency.MONTHLY:
        return nearest_monthly_due_date_instance(due_day, transaction_date)
    assert due_month is not None  # BR-19 guarantees this for annual payments
    return nearest_annual_due_date_instance(due_month, due_day, transaction_date)


def cycle_period_for(frequency: RecurringPaymentFrequency, instance: date) -> str:
    """`"YYYY-MM"` for monthly, `"YYYY"` for annual (WR-17)."""
    if frequency == RecurringPaymentFrequency.MONTHLY:
        return f"{instance.year:04d}-{instance.month:02d}"
    return f"{instance.year:04d}"
