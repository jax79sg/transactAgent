"""Reusable Hypothesis strategies for balances (PBT-07): domain-shaped, not raw primitives. Money is exact two-place
decimals (negative and zero included: an overdrawn account), dates fall in a realistic window with month ends and leap
days well represented, and a known balance carries a source and a record order like the real thing."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from hypothesis import strategies as st

from api_service.balances.calculation import ANCHOR, STATEMENT_CLOSING, KnownBalance

WINDOW_START = date(2023, 1, 1)
WINDOW_END = date(2027, 12, 31)


def money(max_abs: int = 1_000_000):
    """An exact two-place amount in [-max_abs, max_abs], including zero and the extremes."""
    return st.integers(min_value=-max_abs * 100, max_value=max_abs * 100).map(lambda cents: Decimal(cents) / 100)


def flow_amounts():
    """A transaction's signed net amount (inflow positive, outflow negative), never zero."""
    return money(50_000).filter(lambda amount: amount != 0)


def calendar_dates(start: date = WINDOW_START, end: date = WINDOW_END):
    """Dates across a realistic window; month ends and 29 February are drawn on purpose."""
    anywhere = st.dates(min_value=start, max_value=end)
    month_ends = anywhere.map(lambda d: (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1))
    leap_days = st.sampled_from([date(2024, 2, 29), date(2024, 2, 28), date(2024, 3, 1), date(2028, 2, 29)]).filter(
        lambda d: start <= d <= end
    )
    return st.one_of(anywhere, anywhere, month_ends, leap_days)


def known_balances(source: str | None = None):
    """A known balance: an anchor, or a printed closing balance with an id and a record order."""

    def build(balance: Decimal, day: date, source_choice: str, ident: int, order: int) -> KnownBalance:
        return KnownBalance(
            balance=balance,
            date=day,
            source=source_choice,
            statement_id=None if source_choice == ANCHOR else UUID(int=ident),
            recorded_order=order,
        )

    return st.builds(
        build,
        money(),
        calendar_dates(),
        st.just(source) if source else st.sampled_from([ANCHOR, STATEMENT_CLOSING]),
        st.integers(min_value=1, max_value=10_000),
        st.integers(min_value=0, max_value=1_000),
    )


def known_balance_sets(min_size: int = 1, max_size: int = 8):
    """A list of known balances for one account."""
    return st.lists(known_balances(), min_size=min_size, max_size=max_size)


def dated_flows(max_size: int = 60):
    """A list of dated signed flows for one account: {date: total} as the database's daily totals would be."""
    return st.dictionaries(calendar_dates(), flow_amounts(), max_size=max_size)


def date_ranges(max_days: int = 800):
    """A (start, end) pair with start <= end, up to max_days apart."""
    return st.tuples(calendar_dates(), st.integers(min_value=0, max_value=max_days)).map(
        lambda pair: (pair[0], min(pair[0] + timedelta(days=pair[1]), WINDOW_END))
    )
