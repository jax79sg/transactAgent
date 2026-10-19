"""Balance endpoints (Epic 13, AR-55 to AR-62, AR-64): paths, shapes, status and error codes, and that nothing else moved."""

from datetime import date

import pytest
from account_helpers import (
    account_with_history,
    make_account,
    make_section,
    make_tx,
    make_unlinked_tx,
    set_anchor,
)

from api_service.balances import service as balances_service

TODAY = date(2026, 10, 18)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(balances_service, "today_in_reporting_zone", lambda now=None: TODAY)


def main_account(db):
    return account_with_history(
        db, "Main", anchor=("1000.00", date(2026, 6, 30)),
        flows=[(date(2026, 6, 10), "-100.00"), (date(2026, 6, 30), "25.00"), (date(2026, 7, 5), "50.00"), (date(2026, 7, 20), "-20.00")],
    )  # fmt: skip


class TestAccess:
    @pytest.mark.parametrize("path", ["/balances?date=2026-07-01", "/balances/series", "/balances/discrepancies"])
    def test_every_endpoint_needs_a_login(self, client, path):
        assert client.get(path).status_code == 401


class TestBalances:
    def test_the_shape_matches_the_design_field_for_field(self, client, auth_headers, db_session):
        main_account(db_session)
        account_with_history(db_session, "Fresh", identifier="f")  # no anchor
        make_unlinked_tx(db_session, date(2026, 7, 31), "100.00")
        body = client.get("/balances", params={"date": "2026-07-20"}, headers=auth_headers).json()

        assert set(body) == {
            "resolvedDate", "today", "requestedMonth", "ingestedThroughDate", "accounts", "combinedTotalSgd",
            "combinedIncludesCount", "excluded", "hasApproximate", "unlinkedTransactions",
        }  # fmt: skip
        main = next(a for a in body["accounts"] if a["name"] == "Main")
        assert set(main) == {
            "accountId", "name", "bankName", "currency", "status", "balanceNative", "balanceSgd", "isApproximate",
            "fxRateDate", "basis", "latestTransactionDate",
        }  # fmt: skip
        assert (main["status"], main["balanceNative"], main["balanceSgd"], main["isApproximate"]) == ("ok", "1030.00", "1030.00", False)
        assert set(main["basis"]) == {"source", "date", "statementId"} and main["basis"]["source"] == "anchor"
        fresh = next(a for a in body["accounts"] if a["name"] == "Fresh")
        assert (fresh["status"], fresh["balanceSgd"], fresh["basis"]) == ("anchor_required", None, None)
        assert body["combinedTotalSgd"] == "1030.00" and body["combinedIncludesCount"] == 1
        assert [(e["name"], e["reason"]) for e in body["excluded"]] == [("Fresh", "anchor_required")]
        assert (body["resolvedDate"], body["today"], body["ingestedThroughDate"]) == ("2026-07-20", "2026-10-18", "2026-07-31")
        assert set(body["unlinkedTransactions"]) == {"count", "bankNames", "earliestDate", "latestDate", "netByCurrency"}
        assert body["unlinkedTransactions"]["netByCurrency"] == [{"currency": "SGD", "net": "100.00"}]

    def test_a_month_lookup_echoes_the_month_and_resolves_it(self, client, auth_headers, db_session):
        main_account(db_session)
        body = client.get("/balances", params={"month": "2026-07"}, headers=auth_headers).json()
        assert (body["requestedMonth"], body["resolvedDate"], body["combinedTotalSgd"]) == ("2026-07", "2026-07-31", "1030.00")

    @pytest.mark.parametrize(
        ("params", "code"),
        [
            ({}, "date_or_month_required"),
            ({"date": "2026-07-01", "month": "2026-07"}, "date_or_month_required"),
            ({"month": "July"}, "date_or_month_required"),
            ({"date": "2026-10-19"}, "date_in_future"),
            ({"month": "2026-11"}, "month_in_future"),
        ],
    )
    def test_refusals_are_400_with_a_stable_code(self, client, auth_headers, params, code):
        response = client.get("/balances", params=params, headers=auth_headers)
        assert (response.status_code, response.json()["error"]) == (400, code)

    def test_a_malformed_date_is_refused_by_the_framework(self, client, auth_headers):
        assert client.get("/balances", params={"date": "tomorrow"}, headers=auth_headers).status_code == 422

    def test_no_accounts_is_an_empty_result_not_an_error(self, client, auth_headers):
        body = client.get("/balances", params={"date": "2026-07-01"}, headers=auth_headers).json()
        assert (body["accounts"], body["combinedTotalSgd"], body["ingestedThroughDate"], body["unlinkedTransactions"]) == ([], None, None, None)


class TestSeries:
    def test_the_shape_and_the_from_and_to_names(self, client, auth_headers, db_session):
        main_account(db_session)
        account_with_history(db_session, "Fresh", identifier="f")
        body = client.get("/balances/series", params={"from": "2026-07-01", "to": "2026-07-10"}, headers=auth_headers).json()
        assert set(body) == {"start", "end", "granularity", "accounts", "missingAccounts", "points"}
        assert (body["start"], body["end"], body["granularity"]) == ("2026-07-01", "2026-07-10", "day")
        assert len(body["points"]) == 10 and set(body["points"][0]) == {"date", "combinedSgd", "perAccount", "approximateAccountIds"}
        assert [a["name"] for a in body["accounts"]] == ["Main"] and [m["name"] for m in body["missingAccounts"]] == ["Fresh"]
        assert body["points"][4]["combinedSgd"] == "1050.00" and body["points"][4]["date"] == "2026-07-05"  # +50.00 on 5 Jul

    def test_with_no_parameters_it_is_the_last_twelve_months_by_month(self, client, auth_headers, db_session):
        main_account(db_session)
        body = client.get("/balances/series", headers=auth_headers).json()
        assert (body["start"], body["end"], body["granularity"]) == ("2025-10-18", "2026-10-18", "month")

    def test_the_toggle_forces_a_granularity(self, client, auth_headers, db_session):
        main_account(db_session)
        params = {"from": "2026-01-01", "to": "2026-06-30"}  # 180 days: automatic means month ends
        assert client.get("/balances/series", params=params, headers=auth_headers).json()["granularity"] == "month"
        assert client.get("/balances/series", params={**params, "granularity": "day"}, headers=auth_headers).json()["granularity"] == "day"

    @pytest.mark.parametrize(
        ("params", "code"),
        [
            ({"from": "2026-05-02", "to": "2026-05-01"}, "invalid_date_range"),
            ({"from": "2026-05-01", "to": "2026-10-19"}, "invalid_date_range"),
            ({"granularity": "weekly"}, "invalid_date_range"),
            ({"from": "2022-01-01", "to": "2026-10-18", "granularity": "day"}, "range_too_large"),
        ],
    )
    def test_refusals(self, client, auth_headers, params, code):
        response = client.get("/balances/series", params=params, headers=auth_headers)
        assert (response.status_code, response.json()["error"]) == (400, code)

    def test_the_series_path_is_not_swallowed_by_the_lookup_route(self, client, auth_headers):
        assert "points" in client.get("/balances/series", headers=auth_headers).json()


class TestDiscrepancies:
    def test_the_shape(self, client, auth_headers, db_session):
        account = make_account(db_session, name="Gappy")
        set_anchor(db_session, account, "500.00", date(2026, 3, 31))
        section = make_section(db_session, account, closing="1000.00", closing_date=date(2026, 1, 31))
        make_section(db_session, account, closing="800.00", closing_date=date(2026, 2, 28))
        make_tx(db_session, section, date(2026, 3, 10), "-300.00")
        body = client.get("/balances/discrepancies", headers=auth_headers).json()
        assert set(body) == {"tolerance", "accountsChecked", "items"} and body["tolerance"] == "0.00"
        [item] = body["items"]
        assert set(item) == {"accountId", "name", "currency", "statementsChecked", "periodsChecked", "statementDifferences", "periodGaps"}
        assert set(item["statementDifferences"][0]) == {"statementId", "closingDate", "printedBalance", "computedBalance", "difference"}
        assert set(item["periodGaps"][0]) == {"fromStatementId", "toStatementId", "fromDate", "toDate", "printedChange", "transactionNet", "gap"}
        assert item["periodGaps"][0]["gap"] == "-200.00"

    def test_nothing_to_report_is_an_empty_list(self, client, auth_headers):
        assert client.get("/balances/discrepancies", headers=auth_headers).json()["items"] == []


class TestNothingElseMoved:
    """NFR-AB-8: the existing endpoints answer as before."""

    @pytest.mark.parametrize("path", ["/categories", "/settings", "/health", "/version"])
    def test_existing_endpoints_still_answer(self, client, auth_headers, path):
        assert client.get(path, headers=auth_headers).status_code == 200

    def test_the_new_settings_appear_in_the_settings_list(self, client, auth_headers, settings_override_path):
        names = {s["name"] for s in client.get("/settings", headers=auth_headers).json()}
        assert {"reporting_time_zone", "balance_mismatch_tolerance"} <= names
