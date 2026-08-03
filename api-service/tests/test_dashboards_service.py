from datetime import date

import pytest

from api_service.dashboards import service
from api_service.dashboards.schemas import DashboardFilter
from api_service.errors import InvalidCurrencyError


class TestDashboardCurrencyValidation:
    def test_invalid_currency_is_rejected_on_category_trends(self, db_session):
        filters = DashboardFilter(date_from=date(2026, 1, 1), date_to=date(2026, 1, 31), currency="XX")
        with pytest.raises(InvalidCurrencyError):
            service.get_category_trends(db_session, filters)

    def test_empty_range_returns_empty_series(self, db_session):
        filters = DashboardFilter(date_from=date(2020, 1, 1), date_to=date(2020, 1, 2))
        series, disclosure = service.get_cash_flow(db_session, filters)
        assert series == []
        assert disclosure["approximate_count"] == 0
        assert disclosure["excluded_count"] == 0
