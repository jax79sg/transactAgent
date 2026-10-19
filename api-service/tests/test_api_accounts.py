"""Account Management endpoints (Epic 13, AR-51 to AR-54, AR-64): paths, shapes, status codes and error codes."""

import uuid
from datetime import date

import pytest
from account_helpers import (
    account_with_history,
    make_account,
    make_section,
    make_statement,
    set_anchor,
)
from transactagent_db.models import AccountType


def id_of(account):
    return str(account.id)


class TestAccess:
    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            ("get", "/accounts", None),
            ("patch", f"/accounts/{uuid.uuid4()}", {"name": "x"}),
            ("put", f"/accounts/{uuid.uuid4()}/anchor", {"balance": "1.00", "asOfDate": "2026-01-01"}),
            ("post", f"/accounts/{uuid.uuid4()}/merge", {"absorbedAccountId": str(uuid.uuid4())}),
        ],
    )
    def test_every_endpoint_needs_a_login(self, client, method, path, body):
        response = getattr(client, method)(path, json=body) if body else getattr(client, method)(path)
        assert response.status_code == 401

    def test_a_browser_may_send_a_patch_cross_origin_and_an_unknown_method_is_still_not_allowed(self, client):
        from api_service.config import settings

        origin = settings.frontend_origins[0]
        headers = {"Origin": origin, "Access-Control-Request-Headers": "authorization,content-type"}
        allowed = client.options("/accounts/anything", headers={**headers, "Access-Control-Request-Method": "PATCH"})
        assert allowed.status_code == 200 and "PATCH" in allowed.headers["access-control-allow-methods"]
        refused = client.options("/accounts/anything", headers={**headers, "Access-Control-Request-Method": "TRACE"})
        assert refused.status_code == 400


class TestListAccounts:
    def test_the_shape_matches_the_design_field_for_field(self, client, auth_headers, db_session):
        account, _ = account_with_history(db_session, "Main", identifier="4321", flows=[(date(2026, 1, 5), "10")], anchor=("5.00", date(2026, 1, 1)))
        body = client.get("/accounts", headers=auth_headers).json()
        [item] = body["items"]
        assert set(item) == {
            "id", "name", "bankName", "accountIdentifier", "type", "typeSetByUser", "currency", "anchor", "canHaveAnchor",
            "statementCount", "transactionCount", "closingBalanceCount", "latestTransactionDate",
        }  # fmt: skip
        assert set(item["anchor"]) == {"balance", "asOfDate", "updatedAt"}
        assert (item["id"], item["name"], item["accountIdentifier"], item["type"]) == (id_of(account), "Main", "4321", "deposit")
        assert item["anchor"]["balance"] == "5.00" and item["anchor"]["asOfDate"] == "2026-01-01"  # money is an exact string
        assert item["canHaveAnchor"] is True and item["latestTransactionDate"] == "2026-01-05"


class TestUpdateAccount:
    def test_a_rename_and_a_retype(self, client, auth_headers, db_session):
        account = make_account(db_session)
        renamed = client.patch(f"/accounts/{account.id}", json={"name": "Savings"}, headers=auth_headers)
        assert renamed.status_code == 200 and renamed.json()["name"] == "Savings"
        retyped = client.patch(f"/accounts/{account.id}", json={"type": "credit_card"}, headers=auth_headers)
        assert (retyped.json()["type"], retyped.json()["typeSetByUser"], retyped.json()["canHaveAnchor"]) == ("credit_card", True, False)

    @pytest.mark.parametrize(
        ("body", "status", "code"),
        [
            ({}, 400, "nothing_to_change"),
            ({"name": "  "}, 400, "invalid_account_name"),
            ({"type": "savings"}, 400, "invalid_account_type"),
        ],
    )
    def test_refusals(self, client, auth_headers, db_session, body, status, code):
        account = make_account(db_session)
        response = client.patch(f"/accounts/{account.id}", json=body, headers=auth_headers)
        assert (response.status_code, response.json()["error"]) == (status, code)
        assert set(response.json()) == {"error", "message", "details"}  # the one error shape

    def test_an_unknown_account_is_404(self, client, auth_headers):
        response = client.patch(f"/accounts/{uuid.uuid4()}", json={"name": "x"}, headers=auth_headers)
        assert (response.status_code, response.json()["error"]) == (404, "account_not_found")


class TestAnchor:
    def test_set_then_replace_returns_the_previous_one(self, client, auth_headers, db_session):
        account = make_account(db_session)
        url = f"/accounts/{account.id}/anchor"
        first = client.put(url, json={"balance": "100.00", "asOfDate": "2026-06-30"}, headers=auth_headers)
        assert first.status_code == 200 and first.json()["previous"] is None and first.json()["anchor"]["balance"] == "100.00"
        second = client.put(url, json={"balance": 250.5, "asOfDate": "2026-07-31"}, headers=auth_headers)
        assert second.json()["previous"]["balance"] == "100.00" and second.json()["anchor"]["balance"] == "250.50"

    @pytest.mark.parametrize(
        ("body", "status", "code"),
        [
            ({"balance": "abc", "asOfDate": "2026-06-30"}, 400, "invalid_anchor_value"),
            ({"balance": "1.234", "asOfDate": "2026-06-30"}, 400, "invalid_anchor_value"),
            ({"balance": "1.00", "asOfDate": "2999-01-01"}, 400, "anchor_date_in_future"),
            ({"balance": "1.00", "asOfDate": "1999-12-31"}, 400, "anchor_date_out_of_range"),
        ],
    )
    def test_refusals_and_nothing_is_saved(self, client, auth_headers, db_session, body, status, code):
        account = make_account(db_session)
        response = client.put(f"/accounts/{account.id}/anchor", json=body, headers=auth_headers)
        assert (response.status_code, response.json()["error"]) == (status, code)
        assert client.get("/accounts", headers=auth_headers).json()["items"][0]["anchor"] is None

    def test_a_credit_card_cannot_have_one(self, client, auth_headers, db_session):
        account = make_account(db_session, account_type=AccountType.CREDIT_CARD)
        response = client.put(f"/accounts/{account.id}/anchor", json={"balance": "1.00", "asOfDate": "2026-01-01"}, headers=auth_headers)
        assert (response.status_code, response.json()["error"]) == (409, "not_a_deposit_account")

    def test_a_malformed_date_is_refused_by_the_framework_not_saved(self, client, auth_headers, db_session):
        account = make_account(db_session)
        response = client.put(f"/accounts/{account.id}/anchor", json={"balance": "1.00", "asOfDate": "yesterday"}, headers=auth_headers)
        assert response.status_code == 422


class TestMerge:
    def test_a_merge_returns_the_survivor_and_the_absorbed_account_is_gone(self, client, auth_headers, db_session):
        survivor, absorbed = make_account(db_session, name="S", identifier="1"), make_account(db_session, name="A", identifier="2")
        make_section(db_session, absorbed)
        response = client.post(f"/accounts/{survivor.id}/merge", json={"absorbedAccountId": id_of(absorbed)}, headers=auth_headers)
        assert response.status_code == 200 and response.json()["id"] == id_of(survivor) and response.json()["statementCount"] == 1
        assert [a["name"] for a in client.get("/accounts", headers=auth_headers).json()["items"]] == ["S"]

    @pytest.mark.parametrize("kind", ["currency", "together", "choice", "same", "invalid_choice", "missing"])
    def test_each_refusal_has_its_status_and_code_and_changes_nothing(self, client, auth_headers, db_session, kind):
        survivor = make_account(db_session, name="S", identifier="1")
        absorbed = make_account(db_session, name="A", identifier="2", currency="USD" if kind == "currency" else "SGD")
        body = {"absorbedAccountId": id_of(absorbed)}
        expected = {"currency": (409, "merge_currency_mismatch"), "together": (409, "merge_appear_together"),
                    "choice": (409, "merge_anchor_choice_required"), "same": (400, "merge_same_account"),
                    "invalid_choice": (400, "merge_anchor_choice_invalid"), "missing": (404, "account_not_found")}[kind]  # fmt: skip
        if kind == "together":
            shared = make_statement(db_session)
            make_section(db_session, survivor, statement=shared)
            make_section(db_session, absorbed, statement=shared)
        if kind == "choice":
            set_anchor(db_session, survivor, "1.00", date(2026, 1, 1))
            set_anchor(db_session, absorbed, "2.00", date(2026, 1, 1))
        if kind == "same":
            body = {"absorbedAccountId": id_of(survivor)}
        if kind == "invalid_choice":
            body["keepAnchorFrom"] = id_of(survivor)  # neither has an anchor
        if kind == "missing":
            body = {"absorbedAccountId": str(uuid.uuid4())}
        response = client.post(f"/accounts/{survivor.id}/merge", json=body, headers=auth_headers)
        assert (response.status_code, response.json()["error"]) == expected
        assert len(client.get("/accounts", headers=auth_headers).json()["items"]) == 2

    def test_keeping_the_absorbed_accounts_anchor(self, client, auth_headers, db_session):
        survivor, absorbed = make_account(db_session, name="S", identifier="1"), make_account(db_session, name="A", identifier="2")
        set_anchor(db_session, survivor, "1.00", date(2026, 1, 1))
        set_anchor(db_session, absorbed, "2.00", date(2026, 2, 1))
        body = {"absorbedAccountId": id_of(absorbed), "keepAnchorFrom": id_of(absorbed)}
        response = client.post(f"/accounts/{survivor.id}/merge", json=body, headers=auth_headers)
        assert response.json()["anchor"]["balance"] == "2.00"
