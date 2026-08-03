class TestDashboardsApi:
    def test_category_trends_empty_range_returns_empty_series(self, client, auth_headers):
        response = client.get(
            "/dashboards/category-trends",
            params={"date_from": "2020-01-01", "date_to": "2020-01-02"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["series"] == []

    def test_invalid_currency_returns_400(self, client, auth_headers):
        response = client.get(
            "/dashboards/cash-flow",
            params={"date_from": "2026-01-01", "date_to": "2026-01-31", "currency": "zz"},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_currency"
