from datetime import date
from decimal import Decimal
from unittest.mock import patch

from transactagent_db.models import BankStatement, Category, CategorySource, Transaction


def _seed_transaction(db_session, txn_date=date(2026, 1, 15), description="NTUC FAIRPRICE"):
    import uuid

    category = Category(name=f"Groceries-{uuid.uuid4()}", active=True, is_reserved=False)
    db_session.add(category)
    db_session.flush()
    statement = BankStatement(drive_file_id=f"f-{uuid.uuid4()}", pdf_content_hash=uuid.uuid4().hex.ljust(64, "0"))
    db_session.add(statement)
    db_session.flush()
    txn = Transaction(
        bank_statement_id=statement.id,
        transaction_date=txn_date,
        description=description,
        out_flow=Decimal("25.50"),
        currency="SGD",
        bank_name="DBS",
        category_id=category.id,
        category_source=CategorySource.MANUAL,
    )
    db_session.add(txn)
    db_session.flush()
    return txn


class TestAskAiApi:
    def test_requires_auth(self, client):
        response = client.post("/ai/ask", json={"question": "What did I spend on groceries?"})
        assert response.status_code == 401

    def test_ask_with_date_range_returns_grounded_answer(self, client, auth_headers, db_session):
        _seed_transaction(db_session, txn_date=date(2026, 1, 15))

        with patch("api_service.ai_assistant.service.gemini_client.ask_gemini", return_value="You spent $25.50.") as mock_ask:
            response = client.post(
                "/ai/ask",
                json={"question": "How much did I spend?", "dateFrom": "2026-01-01", "dateTo": "2026-01-31"},
                headers=auth_headers,
            )

        assert response.status_code == 200
        body = response.json()
        assert body["answer"] == "You spent $25.50."
        assert body["transactionsConsidered"] == 1
        assert body["truncated"] is False
        # the transaction's own data must actually reach the prompt sent to Gemini
        prompt_sent = mock_ask.call_args[0][0]
        assert "NTUC FAIRPRICE" in prompt_sent
        assert "25.50" in prompt_sent

    def test_missing_date_range_without_use_all_returns_400(self, client, auth_headers, db_session):
        _seed_transaction(db_session)

        response = client.post("/ai/ask", json={"question": "How much did I spend?"}, headers=auth_headers)
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_date_range"

    def test_date_from_after_date_to_returns_400(self, client, auth_headers, db_session):
        _seed_transaction(db_session)

        response = client.post(
            "/ai/ask",
            json={"question": "How much did I spend?", "dateFrom": "2026-02-01", "dateTo": "2026-01-01"},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_date_range"

    def test_no_transactions_in_scope_returns_400(self, client, auth_headers, db_session):
        _seed_transaction(db_session, txn_date=date(2026, 1, 15))

        response = client.post(
            "/ai/ask",
            json={"question": "How much did I spend?", "dateFrom": "2020-01-01", "dateTo": "2020-01-31"},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert response.json()["error"] == "no_transactions_in_scope"

    def test_use_all_transactions_ignores_date_range_entirely(self, client, auth_headers, db_session):
        _seed_transaction(db_session, txn_date=date(2020, 6, 1))  # well outside any plausible range

        with patch("api_service.ai_assistant.service.gemini_client.ask_gemini", return_value="Some answer."):
            response = client.post(
                "/ai/ask", json={"question": "Anything unusual?", "useAllTransactions": True}, headers=auth_headers
            )

        assert response.status_code == 200
        assert response.json()["transactionsConsidered"] == 1

    def test_ai_service_failure_returns_502(self, client, auth_headers, db_session):
        from api_service.errors import AiServiceUnavailableError

        _seed_transaction(db_session)

        with patch(
            "api_service.ai_assistant.service.gemini_client.ask_gemini",
            side_effect=AiServiceUnavailableError("Gemini is down"),
        ):
            response = client.post(
                "/ai/ask",
                json={"question": "How much did I spend?", "dateFrom": "2026-01-01", "dateTo": "2026-01-31"},
                headers=auth_headers,
            )

        assert response.status_code == 502
        assert response.json()["error"] == "ai_service_unavailable"
