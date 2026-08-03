"""Dashboard aggregation business logic (business-logic-model.md — Dashboard/Insights Component).

All three insight types exclude conversion_unavailable transactions from SUMs but
separately count approximate/excluded transactions for the US-4.6 disclosure.
"""

from api_service.dashboards import repository
from api_service.dashboards.schemas import DashboardFilter
from api_service.transactions.service import _validate_currency


def get_category_trends(db, filters: DashboardFilter):
    _validate_currency(filters.currency)
    series = repository.category_trend_series(db, filters)
    disclosure = repository.conversion_disclosure(db, filters)
    return series, disclosure


def get_cash_flow(db, filters: DashboardFilter):
    _validate_currency(filters.currency)
    series = repository.cash_flow_series(db, filters)
    disclosure = repository.conversion_disclosure(db, filters)
    return series, disclosure


def get_bank_breakdown(db, filters: DashboardFilter):
    _validate_currency(filters.currency)
    series = repository.bank_breakdown_series(db, filters)
    disclosure = repository.conversion_disclosure(db, filters)
    return series, disclosure
