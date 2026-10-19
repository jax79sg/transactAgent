"""Issue #28 (Costs page): request filter and response shapes. Money is US dollars, what Google bills, and is never
mixed with the app's SGD figures."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from api_service.schemas import CamelModel

Granularity = Literal["day", "week", "month"]
GroupBy = Literal["none", "purpose", "model"]

# The one group name used when nothing is split out (GroupBy "none").
ALL_GROUP = "All"


class CostsFilter(BaseModel):
    date_from: date
    date_to: date
    granularity: Granularity = "day"
    group_by: GroupBy = "none"
    # IANA name of the viewer's time zone, so a "day" is the viewer's own calendar day (the browser sends it).
    timezone: str = "UTC"


class CostFigures(CamelModel):
    cost_usd: Decimal
    input_tokens: int
    output_tokens: int
    calls: int
    # How many of `calls` have token counts that are estimates (embeddings), so the page can say so.
    estimated_calls: int


class CostPoint(CostFigures):
    period: date  # the day, the Monday of the week, or the first of the month
    group: str


class CostGroupTotal(CostFigures):
    group: str


class CostsResponse(CamelModel):
    currency: Literal["USD"] = "USD"
    date_from: date
    date_to: date
    granularity: Granularity
    group_by: GroupBy
    timezone: str
    periods: list[date]  # every period in the range, including those with no spend, so a chart has no gaps
    totals: CostFigures
    series: list[CostPoint]  # only (period, group) pairs that had calls
    groups: list[CostGroupTotal]  # one per group over the whole range, most expensive first
