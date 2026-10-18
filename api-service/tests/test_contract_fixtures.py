"""Contract drift guard for the Frontend (Epic 13). The Frontend's tests are built on the real responses of the Epic 13
endpoints, committed as JSON in `frontend/tests/fixtures/balances/`; this test rebuilds a fixed scenario, calls each
endpoint and compares the response with that file. If an endpoint's shape changes, THIS test fails; regenerate the
files, and the Frontend's contract test then fails until its types follow. That is what would have caught the
`start`/`end` versus `from`/`to` mistake in the written design, which a hand copy of the design document could not.

Regenerate after a deliberate API change:  UPDATE_CONTRACT_FIXTURES=1 uv run pytest tests/test_contract_fixtures.py
Ids are fixed (not random) and timestamps are replaced, so a regenerated file differs only where the API changed.
"""

import difflib
import json
import os
import re
from datetime import date
from pathlib import Path
from uuid import UUID

import pytest
from account_helpers import (
    make_account,
    make_fx_rate,
    make_section,
    make_statement,
    make_tx,
    make_unlinked_tx,
    set_anchor,
)
from transactagent_db.models import AccountType

from api_service.accounts import service as accounts_service
from api_service.balances import service as balances_service

TODAY = date(2026, 10, 18)
FIXTURE_DIR = Path(__file__).resolve().parents[2] / "frontend" / "tests" / "fixtures" / "balances"
UPDATE = os.environ.get("UPDATE_CONTRACT_FIXTURES") == "1"
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?")

# Every file this module owns. A file on disk that is not listed here is stale; a name listed here must exist.
FIXTURE_NAMES = {
    "accounts-list",
    "balances-date",
    "balances-month",
    "series-day",
    "series-month",
    "discrepancies",
    "anchor-replaced",
    "anchor-created",
    "merge-success",
    "error-merge-appear-together",
    "error-422-date",
}

pytestmark = pytest.mark.skipif(
    not FIXTURE_DIR.parent.parent.exists(),
    reason="the frontend/ directory is not part of this checkout, so there is nothing to compare with",
)


def uid(number: int) -> UUID:
    return UUID(int=number)


MAIN, USD, EUR, FRESH, CARD = uid(1), uid(2), uid(3), uid(4), uid(5)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(balances_service, "today_in_reporting_zone", lambda now=None: TODAY)
    monkeypatch.setattr(accounts_service, "today_in_reporting_zone", lambda now=None: TODAY)


def normalised(payload) -> str:
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    return _TIMESTAMP.sub("2026-01-01T00:00:00Z", text) + "\n"


def check(name: str, payload) -> None:
    assert name in FIXTURE_NAMES, f"{name} is not listed in FIXTURE_NAMES"
    path = FIXTURE_DIR / f"{name}.json"
    text = normalised(payload)
    if UPDATE:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return
    assert path.exists(), f"{path} is missing; create it with UPDATE_CONTRACT_FIXTURES=1"
    expected = path.read_text(encoding="utf-8")
    if expected != text:
        diff = "\n".join(list(difflib.unified_diff(expected.splitlines(), text.splitlines(), "committed", "now", lineterm=""))[:60])
        pytest.fail(
            f"The response for {name} no longer matches {path.name}. If the change is deliberate, regenerate with "
            f"UPDATE_CONTRACT_FIXTURES=1 and update the Frontend's types.\n{diff}"
        )


@pytest.fixture
def scenario(db_session):
    """Five accounts and some unlinked transactions, chosen so every field of every DTO takes an interesting value:
    a statement difference and a period gap, a statement closing as the basis, an approximate SGD figure, an
    unavailable one, an account that needs an anchor, a credit card, and transactions linked to no account."""
    db = db_session
    main = make_account(db, "Main", bank="DBS", identifier="1234", account_id=MAIN)
    first = make_section(db, main, make_statement(db, "DBS", statement_id=uid(101)), closing="1000.00", closing_date=date(2026, 6, 30))
    second = make_section(db, main, make_statement(db, "DBS", statement_id=uid(102)), closing="1100.00", closing_date=date(2026, 7, 31))
    for day, amount in [(date(2026, 6, 10), "-100.00"), (date(2026, 6, 30), "25.00"), (date(2026, 7, 5), "50.00"), (date(2026, 7, 20), "-20.00")]:
        make_tx(db, second, day, amount)
    set_anchor(db, main, "1000.00", date(2026, 6, 30))
    assert first.id != second.id

    usd = make_account(db, "Trust USD", currency="USD", bank="Trust", identifier="usd9", account_id=USD)
    usd_section = make_section(db, usd, make_statement(db, "Trust", statement_id=uid(103)))
    make_tx(db, usd_section, date(2026, 7, 15), "100.00", currency="USD", bank="Trust")
    set_anchor(db, usd, "500.00", date(2026, 7, 1))
    make_fx_rate(db, "USD", date(2026, 7, 20), "1.30")

    eur = make_account(db, "Offshore EUR", currency="EUR", bank="Offshore", identifier="eur1", account_id=EUR)
    make_section(db, eur, make_statement(db, "Offshore", statement_id=uid(104)))
    set_anchor(db, eur, "200.00", date(2026, 7, 1))

    fresh = make_account(db, "Fresh", bank="OCBC", identifier="f001", account_id=FRESH)
    make_section(db, fresh, make_statement(db, "OCBC", statement_id=uid(105)))

    card = make_account(db, "Visa Card", account_type=AccountType.CREDIT_CARD, bank="DBS", identifier="9999", user_set=True, account_id=CARD)
    make_section(db, card, make_statement(db, "DBS", statement_id=uid(106)))

    make_unlinked_tx(db, date(2026, 7, 31), "100.00")
    make_unlinked_tx(db, date(2026, 7, 15), "-5.50", currency="USD")
    return db


class TestReads:
    def test_accounts_list(self, client, auth_headers, scenario):
        check("accounts-list", client.get("/accounts", headers=auth_headers).json())

    def test_balances_for_a_date(self, client, auth_headers, scenario):
        check("balances-date", client.get("/balances", params={"date": "2026-07-31"}, headers=auth_headers).json())

    def test_balances_for_the_current_month(self, client, auth_headers, scenario):
        check("balances-month", client.get("/balances", params={"month": "2026-10"}, headers=auth_headers).json())

    def test_series_daily_with_a_gap(self, client, auth_headers, scenario):
        params = {"from": "2026-07-29", "to": "2026-08-02", "granularity": "day"}
        check("series-day", client.get("/balances/series", params=params, headers=auth_headers).json())

    def test_series_automatic_across_the_anchor_is_monthly(self, client, auth_headers, scenario):
        params = {"from": "2026-05-01", "to": "2026-10-18"}
        check("series-month", client.get("/balances/series", params=params, headers=auth_headers).json())

    def test_discrepancies(self, client, auth_headers, scenario):
        check("discrepancies", client.get("/balances/discrepancies", headers=auth_headers).json())

    def test_a_malformed_date_is_a_framework_422(self, client, auth_headers, scenario):
        response = client.get("/balances", params={"date": "not-a-date"}, headers=auth_headers)
        assert response.status_code == 422
        check("error-422-date", response.json())


class TestWrites:
    def test_replacing_an_anchor(self, client, auth_headers, scenario):
        response = client.put(f"/accounts/{MAIN}/anchor", json={"balance": "1200.00", "asOfDate": "2026-08-31"}, headers=auth_headers)
        assert response.status_code == 200
        check("anchor-replaced", response.json())

    def test_creating_an_anchor(self, client, auth_headers, scenario):
        response = client.put(f"/accounts/{FRESH}/anchor", json={"balance": "250.00", "asOfDate": "2026-08-31"}, headers=auth_headers)
        assert response.status_code == 200
        check("anchor-created", response.json())

    def test_a_merge_that_keeps_one_of_two_anchors(self, client, auth_headers, db_session):
        db = db_session
        survivor = make_account(db, "DBS / POSB 6220", bank="DBS / POSB", identifier="6220", account_id=uid(11))
        absorbed = make_account(db, "DBS 6220", bank="DBS", identifier="6220", account_id=uid(12))
        make_section(db, survivor, make_statement(db, "DBS / POSB", statement_id=uid(111)))
        make_section(db, absorbed, make_statement(db, "DBS", statement_id=uid(112)))
        set_anchor(db, survivor, "500.00", date(2026, 7, 1))
        set_anchor(db, absorbed, "480.00", date(2026, 6, 1))
        body = {"absorbedAccountId": str(absorbed.id), "keepAnchorFrom": str(survivor.id)}
        response = client.post(f"/accounts/{survivor.id}/merge", json=body, headers=auth_headers)
        assert response.status_code == 200
        check("merge-success", response.json())

    def test_a_merge_refused_because_the_accounts_appear_together(self, client, auth_headers, db_session):
        db = db_session
        first = make_account(db, "GXS Bank cket", bank="GXS Bank", identifier="c1", account_id=uid(21))
        second = make_account(db, "GXS Bank cket", bank="GXS Bank", identifier="c2", account_id=uid(22))
        shared = make_statement(db, "GXS Bank", statement_id=uid(121))
        make_section(db, first, shared)
        make_section(db, second, shared)
        response = client.post(f"/accounts/{first.id}/merge", json={"absorbedAccountId": str(second.id)}, headers=auth_headers)
        assert response.status_code == 409
        assert response.json()["error"] == "merge_appear_together"
        check("error-merge-appear-together", response.json())


def test_there_are_no_stale_fixture_files():
    """A committed file nobody regenerates any more would keep the Frontend's contract test passing on old data."""
    if UPDATE or not FIXTURE_DIR.exists():
        return
    on_disk = {path.stem for path in FIXTURE_DIR.glob("*.json")}
    assert on_disk == FIXTURE_NAMES, f"stale: {sorted(on_disk - FIXTURE_NAMES)}, missing: {sorted(FIXTURE_NAMES - on_disk)}"
