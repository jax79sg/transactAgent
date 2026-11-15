from datetime import date
from decimal import Decimal

from transactagent_db.models import BankStatement, Category, CategorySource, Transaction


def _seed_transaction(
    db_session, category_name="Groceries", description="NTUC FAIRPRICE", category=None, bank_name="DBS"
):
    # category/pdf_content_hash are unique-constrained columns -- a caller seeding
    # multiple transactions in one test must pass an existing `category` to reuse (a
    # fresh hash is always generated here, one per call, to dodge that constraint too).
    if category is None:
        category = Category(name=category_name, active=True, is_reserved=False)
        db_session.add(category)
        db_session.flush()
    import uuid

    statement = BankStatement(drive_file_id=f"f-{uuid.uuid4()}", pdf_content_hash=uuid.uuid4().hex.ljust(64, "0"))
    db_session.add(statement)
    db_session.flush()
    txn = Transaction(
        bank_statement_id=statement.id,
        transaction_date=date(2026, 1, 15),
        description=description,
        out_flow=Decimal("25.50"),
        currency="SGD",
        bank_name=bank_name,
        category_id=category.id,
        category_source=CategorySource.SIMILARITY,
    )
    db_session.add(txn)
    db_session.flush()
    return txn, category


class TestTransactionsApi:
    def test_list_transactions_returns_seeded_row(self, client, auth_headers, db_session):
        _seed_transaction(db_session)

        response = client.get("/transactions", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["totalCount"] == 1
        assert body["items"][0]["description"] == "NTUC FAIRPRICE"
        assert body["items"][0]["outFlow"] == "25.50"

    def test_list_transactions_exposes_embedding_status(self, client, auth_headers, db_session):
        """AR-21 (Epic 9): read-only, sourced directly from Transaction.embedding_status
        -- every new row defaults to 'pending' (Database BR-24) until the Ingestion
        Worker's Embedding Manager processes it."""
        _seed_transaction(db_session)

        response = client.get("/transactions", headers=auth_headers)

        assert response.json()["items"][0]["embeddingStatus"] == "pending"

    def test_invalid_currency_filter_returns_400(self, client, auth_headers):
        response = client.get("/transactions", params={"currency": "nope"}, headers=auth_headers)
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_currency"

    def test_bank_filter_returns_only_matching_bank(self, client, auth_headers, db_session):
        _, category = _seed_transaction(db_session, bank_name="UOB")
        _seed_transaction(db_session, category=category, bank_name="DBS")

        response = client.get("/transactions", params={"bank": "UOB"}, headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["totalCount"] == 1
        assert body["items"][0]["bankName"] == "UOB"

    def test_category_filter_returns_only_matching_category(self, client, auth_headers, db_session):
        _seed_transaction(db_session, category_name="Groceries")
        _seed_transaction(db_session, category_name="Dining Out")

        response = client.get("/transactions", params={"category": "Dining Out"}, headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["totalCount"] == 1
        assert body["items"][0]["category"]["name"] == "Dining Out"


class TestListBanksApi:
    def test_requires_auth(self, client):
        response = client.get("/transactions/banks")
        assert response.status_code == 401

    def test_returns_distinct_sorted_banks(self, client, auth_headers, db_session):
        _, category = _seed_transaction(db_session, bank_name="UOB")
        _seed_transaction(db_session, category=category, bank_name="DBS")
        _seed_transaction(db_session, category=category, bank_name="DBS")  # duplicate, should not repeat

        response = client.get("/transactions/banks", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == ["DBS", "UOB"]

    def test_correct_category_creates_recategorization_job(self, client, auth_headers, db_session):
        txn, _old_category = _seed_transaction(db_session)
        new_category = Category(name="Household", active=True, is_reserved=False)
        db_session.add(new_category)
        db_session.flush()

        response = client.put(
            f"/transactions/{txn.id}/category",
            json={"categoryId": str(new_category.id)},
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["transaction"]["categorySource"] == "manual"
        assert body["recategorizationJobId"]

    def test_correct_category_to_inactive_category_returns_400(self, client, auth_headers, db_session):
        txn, _old_category = _seed_transaction(db_session)
        inactive_category = Category(name="Retired", active=False, is_reserved=False)
        db_session.add(inactive_category)
        db_session.flush()

        response = client.put(
            f"/transactions/{txn.id}/category",
            json={"categoryId": str(inactive_category.id)},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert response.json()["error"] == "inactive_category"


class TestTransactionGrouping:
    """Regression coverage: no test previously exercised group_by at all, and the
    frontend silently ignored the `groups` field entirely -- a user reported grouping
    "did not seem to be working" (aidlc-docs/audit.md). Also covers a real backend bug
    found while investigating: group_by=categorySource selects the raw enum column, and
    str() on a `class X(str, Enum)` member returns "CategorySource.MANUAL", not
    "manual" -- Enum.__str__ wins over str.__str__ in the MRO despite the str mixin."""

    def test_group_by_category_returns_correct_subtotals(self, client, auth_headers, db_session):
        _txn1, groceries = _seed_transaction(db_session, category_name="Groceries", description="NTUC")
        _seed_transaction(db_session, description="Cold Storage", category=groceries)
        _seed_transaction(db_session, category_name="Dining", description="McDonald's")

        response = client.get("/transactions", params={"group_by": "category"}, headers=auth_headers)
        assert response.status_code == 200
        groups = {g["groupKey"]: g for g in response.json()["groups"]}

        assert groups["Groceries"]["transactionCount"] == 2
        assert groups["Groceries"]["subtotalOutFlowSgd"] == "51.00"
        assert groups["Dining"]["transactionCount"] == 1
        assert groups["Dining"]["subtotalOutFlowSgd"] == "25.50"

    def test_group_by_category_source_returns_plain_value_not_python_repr(self, client, auth_headers, db_session):
        _seed_transaction(db_session)  # category_source=SIMILARITY

        response = client.get("/transactions", params={"group_by": "categorySource"}, headers=auth_headers)
        assert response.status_code == 200
        group_keys = [g["groupKey"] for g in response.json()["groups"]]

        assert group_keys == ["similarity"]  # not "CategorySource.SIMILARITY"

    def test_no_group_by_returns_null_groups(self, client, auth_headers, db_session):
        _seed_transaction(db_session)

        response = client.get("/transactions", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["groups"] is None


class TestTransactionsByAccount:
    """Issues #65-#70: the Transactions page can name, and filter by, the same accounts the Balances tab lists."""

    @staticmethod
    def _world(db):
        from account_helpers import (
            make_account,
            make_section,
            make_tx,
            make_unlinked_tx,
        )
        from transactagent_db.models import AccountType

        savings = make_account(db, name="OCBC Bank 5001", bank="OCBC Bank", identifier="5001")
        card = make_account(
            db, name="OCBC Bank 4002", bank="OCBC Bank", identifier="4002", account_type=AccountType.CREDIT_CARD
        )
        idle = make_account(db, name="MariBank 8101", bank="MariBank", identifier="8101")
        savings_section = make_section(db, savings)
        card_section = make_section(db, card)
        make_section(db, idle)  # on a statement, but with no transactions
        make_tx(db, savings_section, date(2026, 1, 5), "-10.00", description="COFFEE", bank="OCBC Bank")
        make_tx(db, savings_section, date(2026, 1, 6), "-20.00", description="LUNCH", bank="OCBC Bank")
        make_tx(db, card_section, date(2026, 1, 7), "-30.00", description="BOOKS", bank="OCBC Bank")
        make_unlinked_tx(db, date(2026, 1, 8), "-40.00", bank="GXS Bank")
        return savings, card, idle

    def test_each_transaction_names_its_account_and_type_and_an_unlinked_one_has_none(
        self, client, auth_headers, db_session
    ):
        savings, card, _ = self._world(db_session)

        items = client.get("/transactions", headers=auth_headers).json()["items"]
        by_description = {item["description"]: item for item in items}

        assert by_description["COFFEE"]["account"] == {"id": str(savings.id), "name": "OCBC Bank 5001", "type": "deposit"}
        assert by_description["BOOKS"]["account"] == {"id": str(card.id), "name": "OCBC Bank 4002", "type": "credit_card"}
        assert by_description["unlinked"]["account"] is None

    def test_account_filter_returns_only_that_accounts_transactions(self, client, auth_headers, db_session):
        savings, card, _ = self._world(db_session)

        body = client.get("/transactions", params={"account_id": str(savings.id)}, headers=auth_headers).json()
        assert body["totalCount"] == 2
        assert {item["description"] for item in body["items"]} == {"COFFEE", "LUNCH"}

        body = client.get("/transactions", params={"account_id": str(card.id)}, headers=auth_headers).json()
        assert [item["description"] for item in body["items"]] == ["BOOKS"]

    def test_an_account_with_no_transactions_gives_an_empty_page_not_an_error(self, client, auth_headers, db_session):
        _, _, idle = self._world(db_session)

        response = client.get("/transactions", params={"account_id": str(idle.id)}, headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["totalCount"] == 0
        assert response.json()["items"] == []

    def test_an_unknown_account_gives_an_empty_page_and_a_malformed_id_is_refused(self, client, auth_headers, db_session):
        self._world(db_session)

        unknown = client.get(
            "/transactions", params={"account_id": "00000000-0000-0000-0000-000000000000"}, headers=auth_headers
        )
        assert unknown.status_code == 200
        assert unknown.json()["totalCount"] == 0

        malformed = client.get("/transactions", params={"account_id": "not-a-uuid"}, headers=auth_headers)
        assert malformed.status_code == 422

    def test_correcting_a_category_still_names_the_account(self, client, auth_headers, db_session):
        from transactagent_db.models import Category, Transaction

        savings, _, _ = self._world(db_session)
        txn = db_session.query(Transaction).filter_by(description="COFFEE").one()
        household = Category(name="Household", active=True, is_reserved=False)
        db_session.add(household)
        db_session.flush()

        response = client.put(
            f"/transactions/{txn.id}/category", json={"categoryId": str(household.id)}, headers=auth_headers
        )

        assert response.status_code == 200
        assert response.json()["transaction"]["account"]["id"] == str(savings.id)

    def test_account_filter_combines_with_the_other_filters(self, client, auth_headers, db_session):
        savings, _, _ = self._world(db_session)

        body = client.get(
            "/transactions", params={"account_id": str(savings.id), "text_search": "LUNCH"}, headers=auth_headers
        ).json()
        assert [item["description"] for item in body["items"]] == ["LUNCH"]

        body = client.get(
            "/transactions", params={"account_id": str(savings.id), "bank": "GXS Bank"}, headers=auth_headers
        ).json()
        assert body["totalCount"] == 0

    def test_account_filter_applies_to_group_totals_and_the_csv_export(self, client, auth_headers, db_session):
        savings, _, _ = self._world(db_session)

        grouped = client.get(
            "/transactions", params={"account_id": str(savings.id), "group_by": "bank"}, headers=auth_headers
        ).json()
        assert [(g["groupKey"], g["transactionCount"]) for g in grouped["groups"]] == [("OCBC Bank", 2)]

        csv_lines = client.get(
            "/transactions/export.csv", params={"account_id": str(savings.id)}, headers=auth_headers
        ).text.strip().splitlines()
        assert len(csv_lines) == 1 + 2  # the header and the two transactions of that account
