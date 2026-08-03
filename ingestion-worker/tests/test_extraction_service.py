"""Tests for extraction/service.py's WR-1/WR-2 branching logic, with the Gemini call
and PDF-to-image conversion mocked (no real network/PDF rendering needed)."""

import json
from unittest.mock import patch

import pytest

from ingestion_worker.extraction.service import ExtractionFailure, extract_statement

_VALID_RESPONSE = {
    "bank_name": "DBS",
    "currency": "SGD",
    "confidence": "high",
    "transactions": [
        {
            "transaction_date": "2026-01-15",
            "description": "NTUC FAIRPRICE",
            "amount": 25.50,
            "direction": "out",
            "printed_converted_amount_sgd": None,
            "confidence": "high",
        }
    ],
}


def _mock_pipeline(gemini_response_text: str):
    """Patches both the PDF->image step (irrelevant to this module's own logic) and
    the Gemini call, returning the given raw text as Gemini's response."""
    return (
        patch("ingestion_worker.extraction.service._pdf_to_page_images", return_value=[b"fake-page-bytes"]),
        patch("ingestion_worker.extraction.service.extract_statement_raw", return_value=gemini_response_text),
    )


class TestExtractStatement:
    def test_valid_response_returns_statement(self):
        p1, p2 = _mock_pipeline(json.dumps(_VALID_RESPONSE))
        with p1, p2:
            result = extract_statement(b"fake-pdf-bytes")

        assert not isinstance(result, ExtractionFailure)
        assert result.bank_name == "DBS"
        assert len(result.transactions) == 1

    def test_markdown_fenced_json_is_stripped(self):
        fenced = "```json\n" + json.dumps(_VALID_RESPONSE) + "\n```"
        p1, p2 = _mock_pipeline(fenced)
        with p1, p2:
            result = extract_statement(b"fake-pdf-bytes")

        assert not isinstance(result, ExtractionFailure)

    def test_invalid_json_is_extraction_failure(self):
        p1, p2 = _mock_pipeline("this is not json at all")
        with p1, p2:
            result = extract_statement(b"fake-pdf-bytes")

        assert isinstance(result, ExtractionFailure)
        assert "schema validation" in result.reason

    def test_missing_bank_name_is_extraction_failure(self):
        response = {**_VALID_RESPONSE, "bank_name": None}
        p1, p2 = _mock_pipeline(json.dumps(response))
        with p1, p2:
            result = extract_statement(b"fake-pdf-bytes")

        assert isinstance(result, ExtractionFailure)
        assert "bank name" in result.reason.lower()

    def test_zero_transactions_is_extraction_failure(self):
        response = {**_VALID_RESPONSE, "transactions": []}
        p1, p2 = _mock_pipeline(json.dumps(response))
        with p1, p2:
            result = extract_statement(b"fake-pdf-bytes")

        assert isinstance(result, ExtractionFailure)
        assert "zero transactions" in result.reason.lower()

    def test_low_confidence_below_threshold_is_extraction_failure(self):
        response = {**_VALID_RESPONSE, "confidence": "low"}
        p1, p2 = _mock_pipeline(json.dumps(response))
        with p1, p2:
            result = extract_statement(b"fake-pdf-bytes")

        assert isinstance(result, ExtractionFailure)
        assert "confidence" in result.reason.lower()

    def test_gemini_call_error_is_extraction_failure(self):
        p1, _ = _mock_pipeline("unused")
        with p1, patch(
            "ingestion_worker.extraction.service.extract_statement_raw", side_effect=RuntimeError("API down")
        ):
            result = extract_statement(b"fake-pdf-bytes")

        assert isinstance(result, ExtractionFailure)
        assert "Gemini call error" in result.reason


class TestNonTransactionLineFiltering:
    """Regression coverage. Two rounds of real, live-database findings so far:
    (1) "Balance brought forward" (CIMB) and "Previous balance" (Trust Bank), one of
    them inflating a single month's cash flow by $100,062.66; (2) after that fix
    shipped, a follow-up live report showed "Balance carried forward" (CIMB) and
    "Total outstanding balance" (Trust Bank) were STILL slipping through -- the first
    pass's patterns were too narrow (exact phrases, not the whole family of
    balance-restatement wording). See aidlc-docs/audit.md 2026-08-02."""

    def _response_with_transactions(self, *transactions: dict) -> dict:
        return {
            "bank_name": "CIMB Bank",
            "currency": "SGD",
            "confidence": "high",
            "transactions": list(transactions),
        }

    def _txn(self, description: str, amount: float = 10.0, direction: str = "out") -> dict:
        return {
            "transaction_date": "2026-01-15",
            "description": description,
            "amount": amount,
            "direction": direction,
            "printed_converted_amount_sgd": None,
            "confidence": "high",
        }

    @pytest.mark.parametrize(
        "description",
        [
            "Balance brought forward",
            "Previous balance",
            "Opening balance",
            "Closing balance",
            "Balance carried forward",  # round-2 finding: "carried", not "brought"
            "Total outstanding balance",  # round-2 finding
            "Outstanding balance",
            "BAL B/F",
            "Bal c/f",
        ],
    )
    def test_balance_restatement_lines_are_dropped(self, description):
        response = self._response_with_transactions(
            self._txn(description, amount=100062.66, direction="in"),
            self._txn("NTUC FAIRPRICE"),
        )
        p1, p2 = _mock_pipeline(json.dumps(response))
        with p1, p2:
            result = extract_statement(b"fake-pdf-bytes")

        assert not isinstance(result, ExtractionFailure)
        assert len(result.transactions) == 1
        assert result.transactions[0].description == "NTUC FAIRPRICE"

    def test_a_statement_with_only_a_balance_line_is_a_zero_transaction_failure(self):
        response = self._response_with_transactions(self._txn("Balance carried forward"))
        p1, p2 = _mock_pipeline(json.dumps(response))
        with p1, p2:
            result = extract_statement(b"fake-pdf-bytes")

        assert isinstance(result, ExtractionFailure)
        assert "zero transactions" in result.reason.lower()

    def test_a_real_purchase_mentioning_balance_is_not_dropped(self):
        # "balance" alone must not be treated as a trigger word -- only the specific
        # restatement phrasings are.
        response = self._response_with_transactions(self._txn("BALANCE FITNESS STUDIO"))
        p1, p2 = _mock_pipeline(json.dumps(response))
        with p1, p2:
            result = extract_statement(b"fake-pdf-bytes")

        assert not isinstance(result, ExtractionFailure)
        assert len(result.transactions) == 1


class TestDayMonthSwapRepair:
    """Regression coverage for a real failure: Gemini extracted every date in an OCBC
    statement (day-first-printed dates) with day and month transposed for the *whole*
    document -- "2026-13-01" through "2026-31-01", not random per-transaction noise.
    See aidlc-docs/audit.md 2026-08-02."""

    def _response_with_dates(self, *dates: str) -> dict:
        return {
            "bank_name": "OCBC",
            "currency": "SGD",
            "confidence": "high",
            "transactions": [
                {
                    "transaction_date": d,
                    "description": f"TXN {i}",
                    "amount": 10.00,
                    "direction": "out",
                    "printed_converted_amount_sgd": None,
                    "confidence": "high",
                }
                for i, d in enumerate(dates)
            ],
        }

    def test_unambiguously_swapped_dates_are_repaired(self):
        # "2026-13-01" can't be month=13 -- this is the actual failure pattern (day
        # value correct, sitting in the month slot, for every transaction)
        response = self._response_with_dates("2026-13-01", "2026-31-01", "2026-05-01")
        p1, p2 = _mock_pipeline(json.dumps(response))
        with p1, p2:
            result = extract_statement(b"fake-pdf-bytes")

        assert not isinstance(result, ExtractionFailure)
        dates = [str(t.transaction_date) for t in result.transactions]
        assert dates == ["2026-01-13", "2026-01-31", "2026-01-05"]

    def test_already_correct_dates_are_left_untouched(self):
        # No unambiguous evidence of a swap (every month value is already <=12) --
        # must not "fix" data that was never broken.
        response = self._response_with_dates("2026-01-15", "2026-02-03")
        p1, p2 = _mock_pipeline(json.dumps(response))
        with p1, p2:
            result = extract_statement(b"fake-pdf-bytes")

        assert not isinstance(result, ExtractionFailure)
        dates = [str(t.transaction_date) for t in result.transactions]
        assert dates == ["2026-01-15", "2026-02-03"]

    def test_a_still_invalid_date_after_swap_still_fails(self):
        # Both components out of range for a month (13 and 32) -- swapping can't
        # rescue this, and it must not be silently accepted as some other date.
        response = self._response_with_dates("2026-13-32")
        p1, p2 = _mock_pipeline(json.dumps(response))
        with p1, p2:
            result = extract_statement(b"fake-pdf-bytes")

        assert isinstance(result, ExtractionFailure)
        assert "schema validation" in result.reason
