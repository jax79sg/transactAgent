from datetime import date
from decimal import Decimal
from uuid import uuid4

from api_service.ai_assistant.prompts import build_prompt
from transactagent_db.models import Category, Transaction


def _txn(
    description="NTUC FAIRPRICE",
    out_flow=Decimal("25.50"),
    in_flow=None,
    converted=Decimal("25.50"),
    category_name="Groceries",
):
    txn = Transaction(
        id=uuid4(),
        bank_statement_id=uuid4(),
        transaction_date=date(2026, 1, 15),
        description=description,
        out_flow=out_flow,
        in_flow=in_flow,
        currency="SGD",
        bank_name="DBS",
        category_id=uuid4(),
        category_source="manual",
        converted_amount_sgd=converted,
    )
    # category is a relationship, not a plain column -- set directly for this
    # in-memory (never-flushed) object rather than round-tripping through a real DB
    txn.category = Category(id=uuid4(), name=category_name, active=True, is_reserved=False)
    return txn


class TestBuildPrompt:
    def test_includes_transaction_data_in_the_prompt(self):
        prompt = build_prompt("How much on groceries?", [_txn()], truncated=False, scope_description="2026-01-01 to 2026-01-31")

        assert "NTUC FAIRPRICE" in prompt
        assert "25.50" in prompt
        assert "Groceries" in prompt
        assert "How much on groceries?" in prompt
        assert "2026-01-01 to 2026-01-31" in prompt

    def test_in_flow_transactions_are_labeled_correctly(self):
        prompt = build_prompt(
            "Any income?", [_txn(description="Salary", out_flow=None, in_flow=Decimal("5000.00"))],
            truncated=False, scope_description="all transactions",
        )

        assert ",in,5000.00," in prompt

    def test_out_flow_transactions_are_labeled_correctly(self):
        prompt = build_prompt("Spending?", [_txn()], truncated=False, scope_description="all transactions")

        assert ",out,25.50," in prompt

    def test_description_containing_a_comma_is_quoted_for_csv_safety(self):
        prompt = build_prompt(
            "What is this?", [_txn(description='Store, Inc "Sale"')], truncated=False, scope_description="all transactions",
        )

        # a raw unescaped comma/quote in the description would corrupt the CSV
        # structure -- the quote must be doubled per CSV convention
        assert '"Store, Inc ""Sale"""' in prompt

    def test_truncation_note_present_only_when_truncated(self):
        truncated_prompt = build_prompt("Q", [_txn()], truncated=True, scope_description="all transactions")
        full_prompt = build_prompt("Q", [_txn()], truncated=False, scope_description="all transactions")

        assert "left out to keep this within size limits" in truncated_prompt
        assert "left out to keep this within size limits" not in full_prompt

    def test_instructs_the_model_not_to_give_authoritative_financial_advice(self):
        prompt = build_prompt("Q", [_txn()], truncated=False, scope_description="all transactions")

        assert "not a licensed financial advisor" in prompt
