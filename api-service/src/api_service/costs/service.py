"""Costs page business logic: validate the request, turn the viewer's calendar days into UTC bounds, aggregate, and
list every period in the range so the chart has no gaps."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from api_service.costs import repository
from api_service.costs.schemas import (
    CostFigures,
    CostGroupTotal,
    CostPoint,
    CostsFilter,
    CostsResponse,
)
from api_service.errors import InvalidDateRangeError, InvalidTimeZoneError

_ZERO = {"cost_usd": Decimal(0), "input_tokens": 0, "output_tokens": 0, "calls": 0, "estimated_calls": 0}


def _period_start(day: date, granularity: str) -> date:
    if granularity == "week":
        return day - timedelta(days=day.weekday())  # Monday
    if granularity == "month":
        return day.replace(day=1)
    return day


def _next_period(period: date, granularity: str) -> date:
    if granularity == "week":
        return period + timedelta(days=7)
    if granularity == "month":
        return date(period.year + (period.month == 12), period.month % 12 + 1, 1)
    return period + timedelta(days=1)


def list_periods(date_from: date, date_to: date, granularity: str) -> list[date]:
    periods = []
    period = _period_start(date_from, granularity)
    while period <= date_to:
        periods.append(period)
        period = _next_period(period, granularity)
    return periods


def _add(totals: dict, row: dict) -> None:
    for key in _ZERO:
        totals[key] += row[key]


def get_costs(db: Session, filters: CostsFilter) -> CostsResponse:
    if filters.date_from > filters.date_to:
        raise InvalidDateRangeError("date_from must not be after date_to")
    try:
        zone = ZoneInfo(filters.timezone)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise InvalidTimeZoneError(f"Unknown time zone: {filters.timezone!r}") from exc

    # The viewer's calendar days [date_from, date_to] as an instant range, so the index on occurred_at is used.
    start = datetime.combine(filters.date_from, time.min, tzinfo=zone)
    end = datetime.combine(filters.date_to + timedelta(days=1), time.min, tzinfo=zone)
    rows = repository.usage_by_period_and_group(
        db, start=start, end=end, granularity=filters.granularity, group_by=filters.group_by,
        timezone=filters.timezone,
    )

    totals = dict(_ZERO)
    per_group: dict[str, dict] = {}
    for row in rows:
        _add(totals, row)
        _add(per_group.setdefault(row["group"], dict(_ZERO)), row)
    groups = sorted(per_group.items(), key=lambda item: (-item[1]["cost_usd"], item[0]))

    return CostsResponse(
        date_from=filters.date_from,
        date_to=filters.date_to,
        granularity=filters.granularity,
        group_by=filters.group_by,
        timezone=filters.timezone,
        periods=list_periods(filters.date_from, filters.date_to, filters.granularity),
        totals=CostFigures(**totals),
        series=[CostPoint(**row) for row in rows],
        groups=[CostGroupTotal(group=name, **figures) for name, figures in groups],
    )
