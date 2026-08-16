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
