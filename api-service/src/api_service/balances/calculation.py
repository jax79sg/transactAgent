"""Pure arithmetic for account balances (Epic 13, AR-55 to AR-57, AR-59, AR-61, AR-62).

Nothing here touches the database or the clock: every function takes what it needs as arguments and returns exact
`Decimal` results (NFR-AB-1), so each one can be tested on its own and by property (NFR-AB-4). The services supply the
data (known balances, daily flow totals) and "today"; they translate the exceptions below into API errors (AR-64).

The one rounding anywhere is the conversion to SGD (`to_sgd`, AR-59).
"""

import calendar
from bisect import bisect_right
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from itertools import accumulate, pairwise
from uuid import UUID

CENT = Decimal("0.01")
EARLIEST_DATE = date(2000, 1, 1)
AUTO_DAILY_MAX_DAYS = 92  # AR-61: `auto` plots every day up to this range length, month ends beyond it
MAX_SERIES_POINTS = 1500  # AR-61
DEFAULT_SERIES_MONTHS = 12  # AR-61 / Question 2 = A

ANCHOR = "anchor"
STATEMENT_CLOSING = "statement_closing"

DAY = "day"
MONTH = "month"
AUTO = "auto"

NetFlow = Callable[[date, date], Decimal]  # (after, through] -> inflows minus outflows


class CalculationError(ValueError):
    """Base of the refusals below; each carries the stable API error code the service maps it to (AR-64)."""

    code = "invalid_input"


class DateInFuture(CalculationError):
    code = "date_in_future"


class MonthInFuture(CalculationError):
    code = "month_in_future"


class DateOutOfRange(CalculationError):
    code = "invalid_date_range"


class InvalidDateRange(CalculationError):
    code = "invalid_date_range"


class RangeTooLarge(CalculationError):
    code = "range_too_large"


class InvalidMonth(CalculationError):
    code = "date_or_month_required"


@dataclass(frozen=True)
class KnownBalance:
    """An end-of-day balance the account is known to have had: the manual anchor, or a printed statement closing
    balance (AR-55). `recorded_order` breaks a tie between two printed balances on the same date: the larger was
    recorded later."""

    balance: Decimal
    date: date
    source: str  # ANCHOR or STATEMENT_CLOSING
    statement_id: UUID | None = None
    recorded_order: int = 0


@dataclass(frozen=True)
class StatementDifference:
    statement_id: UUID | None
    closing_date: date
    printed_balance: Decimal
    computed_balance: Decimal
    difference: Decimal  # printed minus computed


@dataclass(frozen=True)
class PeriodGap:
    from_statement_id: UUID | None
    to_statement_id: UUID | None
    from_date: date
    to_date: date
    printed_change: Decimal
    transaction_net: Decimal
    gap: Decimal  # printed change minus transaction net


# ------------------------------------------------------------------------------------------- the balance (AR-55, AR-56)


def flow_interval(known_date: date, target: date) -> tuple[date, date]:
    """The interval whose net flow links the known date and the target: (after, through], the earlier date excluded
    and the later one included, whichever way round they are."""
    return (known_date, target) if target >= known_date else (target, known_date)


def balance_from_known(known_balance: Decimal, known_date: date, target: date, net_flow: Decimal) -> Decimal:
    """FR-AB-7. `net_flow` is the net of inflows minus outflows over `flow_interval(known_date, target)`. On or after
    the known date it is added; before it, subtracted."""
    return known_balance + net_flow if target >= known_date else known_balance - net_flow


def deduplicate_by_date(known: Sequence[KnownBalance]) -> list[KnownBalance]:
    """At most one known balance per date: the manual anchor if there is one, otherwise the one recorded last (AR-55).
    Returned in date order."""
    best: dict[date, KnownBalance] = {}
    for k in known:
        current = best.get(k.date)
        if current is None or _preferred_over(k, current):
            best[k.date] = k
    return [best[d] for d in sorted(best)]


def _preferred_over(candidate: KnownBalance, current: KnownBalance) -> bool:
    if (candidate.source == ANCHOR) != (current.source == ANCHOR):
        return candidate.source == ANCHOR
    if candidate.recorded_order != current.recorded_order:
        return candidate.recorded_order > current.recorded_order
    return str(candidate.statement_id) > str(current.statement_id)  # last resort, only to be deterministic


def choose_reference(known: Sequence[KnownBalance], target: date) -> KnownBalance:
    """The known balance nearest the target in calendar days; a tie goes to the manual anchor, then to the earlier date
    (AR-55). The result does not depend on the order of `known`."""
    candidates = deduplicate_by_date(known)
    if not candidates:
        raise ValueError("no known balance to work from")
    return min(candidates, key=lambda k: (abs((k.date - target).days), 0 if k.source == ANCHOR else 1, k.date))


def balance_on_date(known: Sequence[KnownBalance], target: date, net_flow: NetFlow) -> tuple[Decimal, KnownBalance]:
    """The end-of-day balance on `target` and the known balance it was worked from (AR-55, AR-56). `net_flow(after,
    through)` supplies the account's net flow; this function never sees a transaction."""
    reference = choose_reference(known, target)
    after, through = flow_interval(reference.date, target)
    return balance_from_known(reference.balance, reference.date, target, net_flow(after, through)), reference


def to_sgd(amount: Decimal, rate: Decimal) -> Decimal:
    """AR-59: the native balance times the rate, rounded half-up to two places. The only rounding in the feature."""
    return (amount * rate).quantize(CENT, rounding=ROUND_HALF_UP)


class NetFlowIndex:
    """Net flow over any interval from per-day totals, by prefix sums: the series and the discrepancy views ask for
    many intervals, and this answers each without touching the database again (AR-66). Exact decimals throughout."""

    def __init__(self, daily_totals: Mapping[date, Decimal]) -> None:
        self._dates = sorted(daily_totals)
        # _prefix[i] is the total of the first i days, so _prefix[0] is zero and there is one more entry than days
        self._prefix = list(accumulate((daily_totals[d] for d in self._dates), initial=Decimal(0)))

    def _total_through(self, day: date) -> Decimal:
        return self._prefix[bisect_right(self._dates, day)]  # bisect_right = how many days are on or before `day`

    def net(self, after: date, through: date) -> Decimal:
        """Inflows minus outflows dated after `after` up to and including `through`."""
        if through <= after:
            return Decimal(0)
        return self._total_through(through) - self._total_through(after)


# ------------------------------------------------------------------------------------- dates (AR-57, AR-61)


def add_months(day: date, months: int) -> date:
    """The same day-of-month `months` later (or earlier), or the month's last day when it has no such day."""
    index = day.year * 12 + (day.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def month_end(day: date) -> date:
    return date(day.year, day.month, calendar.monthrange(day.year, day.month)[1])


def parse_month(text: str) -> tuple[int, int]:
    """`YYYY-MM` to (year, month); anything else is refused."""
    try:
        year_text, month_text = text.split("-")
        year, month = int(year_text), int(month_text)
        if len(year_text) != 4 or len(month_text) != 2 or not 1 <= month <= 12 or year < EARLIEST_DATE.year:
            raise ValueError
    except ValueError as exc:
        raise InvalidMonth(f"{text!r} is not a month in the form YYYY-MM") from exc
    return year, month


def resolve_month(month_text: str, today: date) -> date:
    """A-5: the last day of a past month; today for the current month; a later month is refused."""
    year, month = parse_month(month_text)
    if (year, month) > (today.year, today.month):
        raise MonthInFuture(f"{month_text} is after the current month")
    if (year, month) == (today.year, today.month):
        return today
    return date(year, month, calendar.monthrange(year, month)[1])


def validate_lookup_date(target: date, today: date) -> date:
    """AR-57: not after today and not before 2000-01-01."""
    if target > today:
        raise DateInFuture(f"{target.isoformat()} is after today ({today.isoformat()})")
    if target < EARLIEST_DATE:
        raise DateOutOfRange(f"{target.isoformat()} is before {EARLIEST_DATE.isoformat()}")
    return target


def default_series_range(today: date) -> tuple[date, date]:
    """AR-61: the last twelve months, ending today."""
    return add_months(today, -DEFAULT_SERIES_MONTHS), today


def resolve_granularity(start: date, end: date, requested: str) -> str:
    """`auto` is every day for ranges of 92 days or fewer, month ends beyond that (AR-61)."""
    if requested == AUTO:
        return DAY if (end - start).days <= AUTO_DAILY_MAX_DAYS else MONTH
    if requested in (DAY, MONTH):
        return requested
    raise InvalidDateRange(f"unknown granularity {requested!r}")


def series_dates(start: date, end: date, granularity: str) -> list[date]:
    """The dates a series plots, in order. Day: every day from start to end. Month: the last day of every month
    that falls inside the range, plus the end date when it is not itself a month end, so the line reaches the end of
    the range and never plots a future month end (AR-61)."""
    if granularity == DAY:
        return [start + timedelta(days=i) for i in range((end - start).days + 1)]
    if granularity != MONTH:
        raise InvalidDateRange(f"unknown granularity {granularity!r}")
    dates: list[date] = []
    cursor = month_end(start)
    while cursor <= end:
        dates.append(cursor)
        cursor = month_end(add_months(cursor, 1))
    if not dates or dates[-1] != end:
        dates.append(end)
    return dates


def validate_series_range(start: date, end: date, today: date, granularity: str) -> list[date]:
    """Check the range (AR-61) and return the dates to plot."""
    if start > end:
        raise InvalidDateRange("the start of the range is after its end")
    if end > today:
        raise InvalidDateRange(f"the end of the range is after today ({today.isoformat()})")
    if start < EARLIEST_DATE:
        raise DateOutOfRange(f"{start.isoformat()} is before {EARLIEST_DATE.isoformat()}")
    if granularity == DAY and (end - start).days + 1 > MAX_SERIES_POINTS:
        raise RangeTooLarge(f"a daily series is limited to {MAX_SERIES_POINTS} points")
    dates = series_dates(start, end, granularity)
    if len(dates) > MAX_SERIES_POINTS:
        raise RangeTooLarge(f"a series is limited to {MAX_SERIES_POINTS} points")
    return dates


# ------------------------------------------------------------------------------------------ discrepancies (AR-62)


def statement_differences(
    anchor: KnownBalance, closings: Sequence[KnownBalance], net_flow: NetFlow, tolerance: Decimal
) -> list[StatementDifference]:
    """FR-AB-8: for each printed closing balance, the balance computed from the ANCHOR ALONE on that date (not the
    nearest-known-balance rule, AR-55) and the difference, listed when it exceeds the tolerance."""
    found = []
    for closing in deduplicate_by_date(closings):
        after, through = flow_interval(anchor.date, closing.date)
        computed = balance_from_known(anchor.balance, anchor.date, closing.date, net_flow(after, through))
        difference = closing.balance - computed
        if abs(difference) > tolerance:
            found.append(StatementDifference(closing.statement_id, closing.date, closing.balance, computed, difference))
    return found


def period_gaps(closings: Sequence[KnownBalance], net_flow: NetFlow, tolerance: Decimal) -> list[PeriodGap]:
    """For each pair of consecutive printed closing balances of one account: the change in the printed balance
    against the net of the transactions between them. A gap marks the interval where transactions are missing or
    mis-dated; it does not depend on the anchor (AR-62)."""
    ordered = deduplicate_by_date(closings)
    found = []
    for earlier, later in pairwise(ordered):
        printed_change = later.balance - earlier.balance
        net = net_flow(earlier.date, later.date)
        gap = printed_change - net
        if abs(gap) > tolerance:
            found.append(
                PeriodGap(earlier.statement_id, later.statement_id, earlier.date, later.date, printed_change, net, gap)
            )
    return found
