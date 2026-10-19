"""Aggregation of the model_usage ledger for the Costs page (Repository Layer)."""

from datetime import datetime

from sqlalchemy import Date, Integer, case, cast, func, literal_column, select
from sqlalchemy.orm import Session
from transactagent_db.models import ModelUsage

from api_service.costs.schemas import ALL_GROUP, GroupBy


def usage_by_period_and_group(
    db: Session, *, start: datetime, end: datetime, granularity: str, group_by: GroupBy, timezone: str
) -> list[dict]:
    """One row per (period, group) that had calls in [start, end). `period` is the start of the day / ISO week
    (Monday) / month in `timezone`, so a call made at 01:00 Singapore time on the 6th is on the 6th, not the 5th."""
    # Built once and reused for select/group_by/order_by -- see dashboards/repository.py for why.
    local_time = func.timezone(timezone, ModelUsage.occurred_at)
    period = cast(func.date_trunc(granularity, local_time), Date)
    # "none" is a constant, which Postgres refuses in ORDER BY and would read as a column position in GROUP BY, so it
    # is selected but never grouped or ordered on: every row is in the one group anyway.
    group_columns = {"none": [], "purpose": [ModelUsage.purpose], "model": [ModelUsage.model]}[group_by]
    group = group_columns[0] if group_columns else literal_column(f"'{ALL_GROUP}'")
    stmt = (
        select(
            period.label("period"),
            group.label("group"),
            func.sum(ModelUsage.cost_usd).label("cost_usd"),
            func.sum(ModelUsage.input_tokens).label("input_tokens"),
            func.sum(ModelUsage.output_tokens).label("output_tokens"),
            func.count().label("calls"),
            func.sum(case((ModelUsage.tokens_estimated.is_(True), 1), else_=0).cast(Integer)).label("estimated_calls"),
        )
        .where(ModelUsage.occurred_at >= start, ModelUsage.occurred_at < end)
        .group_by(period, *group_columns)
        .order_by(period, *group_columns)
    )
    return [
        {
            "period": r.period, "group": r.group, "cost_usd": r.cost_usd, "input_tokens": int(r.input_tokens),
            "output_tokens": int(r.output_tokens), "calls": r.calls, "estimated_calls": int(r.estimated_calls),
        }
        for r in db.execute(stmt)
    ]
