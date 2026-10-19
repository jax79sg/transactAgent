"""Tests for extraction/service.py's WR-1/WR-2 branching logic, with the Gemini call
and PDF-to-image conversion mocked (no real network/PDF rendering needed)."""

import json
from datetime import date, timedelta
from decimal import Decimal
from typing import ClassVar
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


class TestFutureDatedTransactionFiltering:
    """Regression coverage for the last-resort safety net: whatever the cause, a
    transaction_date after today must never reach the database. (The real root
    cause turned out to be the per-transaction ambiguous-date misread covered by
    TestAmbiguousDateCorrection below, confirmed live against two real OCBC
    statements -- see the 2026-08-04 investigation in aidlc-docs/audit.md. This
    filter remains as a backstop for cases that correction can't resolve, e.g. the
    excluded administrative/fee lines.)"""

    def _response_with_dates(self, *dates: str) -> dict:
        return {
            "bank_name": "OCBC Bank",
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

    def test_future_dated_transactions_are_dropped(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        next_month = (date.today() + timedelta(days=45)).isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        response = self._response_with_dates(yesterday, tomorrow, next_month)
        p1, p2 = _mock_pipeline(json.dumps(response))
        with p1, p2:
            result = extract_statement(b"fake-pdf-bytes")

        assert not isinstance(result, ExtractionFailure)
        assert len(result.transactions) == 1
        assert str(result.transactions[0].transaction_date) == yesterday

    def test_todays_date_is_not_dropped(self):
        today = date.today().isoformat()
        response = self._response_with_dates(today)
        p1, p2 = _mock_pipeline(json.dumps(response))
        with p1, p2:
            result = extract_statement(b"fake-pdf-bytes")

        assert not isinstance(result, ExtractionFailure)
        assert len(result.transactions) == 1

    def test_a_statement_with_only_future_dates_is_a_zero_transaction_failure(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        response = self._response_with_dates(tomorrow)
        p1, p2 = _mock_pipeline(json.dumps(response))
        with p1, p2:
            result = extract_statement(b"fake-pdf-bytes")

        assert isinstance(result, ExtractionFailure)
        assert "zero transactions" in result.reason.lower()


class TestAmbiguousDateCorrection:
    """Golden-data regression coverage built directly from a real OCBC statement PDF
    (statement date 01-02-2026), reconstructed by downloading the actual source file
    via the app's own Drive connection and cross-checking every printed transaction
    date against what actually got committed to the live database. Real, live
    failure: Gemini parsed unambiguous dates (printed day > 12) correctly day-first,
    but for individually-ambiguous dates (printed day <= 12) within the SAME
    document it inconsistently fell back to month-first -- e.g. "3 January" (printed
    "03/01") committed as 2026-03-01 (March 3rd... actually March 1st, day/month
    swapped) instead of 2026-01-03. Every date/description pair below is the exact
    (buggy, as actually emitted) value paired with the true calendar date read
    directly off the statement page. See aidlc-docs/audit.md 2026-08-04.

    "literal" below is what Gemini actually emitted (== what's still sitting in the
    live database, unfixed, at the time this test was written) for each entry;
    "expected" is the true date printed on the statement."""

    # (literal transaction_date as Gemini emitted it, description, amount, expected corrected date)
    _REAL_STATEMENT_SEQUENCE: ClassVar[list[tuple[str, str, float, str]]] = [
        ("2026-02-01", "PAYMENT BY INTERNET", 1056.10, "2026-02-01"),  # excluded (payment) -- already correct
        ("2025-12-31", "-0773 BUS/MRT 771790695", 1.28, "2025-12-31"),  # unambiguous (day>12), trusted as-is
        ("2026-01-01", "-0773 VISTA PANCAKES PTE", 7.80, "2026-01-01"),  # day==month, no-op
        ("2026-01-01", "-0773 PRIMEST", 1.00, "2026-01-01"),
        ("2026-02-01", "UOI-FIPP 01/26 PPA", 27.25, "2026-01-02"),  # buggy: real date is 2 Jan
        ("2026-02-01", "-5138 PARKING.SG BILL C6D", 1.06, "2026-01-02"),
        ("2026-02-01", "-0773 BUS/MRT 772819402", 1.57, "2026-01-02"),
        ("2026-03-01", "-0773 IKEA-RESTAURANT", 53.90, "2026-01-03"),  # buggy: real date is 3 Jan
        ("2026-03-01", "-0773 FAIRPRICE XTRA-KALL", 4.70, "2026-01-03"),
        ("2026-04-01", "-0773 BEARD PAPA'S - PARK", 19.00, "2026-01-04"),
        ("2026-05-01", "-2182 NETFLIX.COM", 37.96, "2026-01-05"),
        ("2026-05-01", "-0773 BUS/MRT 774331564", 3.59, "2026-01-05"),
        ("2026-06-01", "ABECHA-FUEL @ ESSO/MOBIL", 90.50, "2026-01-06"),
        ("2026-06-01", "-0773 FENG SHENG", 4.40, "2026-01-06"),
        ("2026-07-01", "-0773 GARDENIA FOODS S PT", 3.10, "2026-01-07"),
        ("2026-08-01", "-0773 BUS/MRT 776161939", 3.82, "2026-01-08"),
        ("2026-09-01", "-1866 ZERO1 PTE LTD", 12.00, "2026-01-09"),
        ("2026-10-01", "-0773 BUS/MRT 777615482", 1.28, "2026-01-10"),
        ("2026-11-01", "APPLE.COM/BILL", 1.48, "2026-01-11"),
        ("2026-12-01", "-2216 PAYPAL *RELATIO 2NH", 26.86, "2026-01-12"),
        ("2026-12-01", "-0773 BUS/MRT 778575144", 3.59, "2026-01-12"),
        ("2026-01-13", "ABECHA-FUEL @ ESSO/MOBIL", 90.18, "2026-01-13"),  # unambiguous again, trusted
        ("2026-01-13", "-0773 BUS/MRT 779207868", 1.57, "2026-01-13"),
        ("2026-01-14", "-0773 BUS/MRT 779822063", 3.59, "2026-01-14"),
        ("2026-01-24", "-0773 POPULAR BOOK COMPAN", 34.72, "2026-01-24"),
        ("2026-01-31", "-0773 KOPI KORNER F", 1.90, "2026-01-31"),
        ("2026-02-01", "INTEREST CHARGE", 25.00, "2026-02-01"),  # excluded (interest) -- already correct
    ]

    def test_real_statement_sequence_is_corrected_to_true_dates(self):
        # All of the dates above are safely in the past (2025/2026 relative to any
        # real "today"), so the pre-existing future-date safety net never engages
        # here -- this test is purely about the correction pass.
        response = {
            "bank_name": "OCBC Bank",
            "currency": "SGD",
            "statement_date": "2026-02-01",
            "confidence": "high",
            "transactions": [
                {
                    "transaction_date": literal,
                    "description": desc,
                    "amount": amount,
                    "direction": "out",
                    "printed_converted_amount_sgd": None,
                    "confidence": "high",
                }
                for literal, desc, amount, _expected in self._REAL_STATEMENT_SEQUENCE
            ],
        }
        p1, p2 = _mock_pipeline(json.dumps(response))
        with p1, p2:
            result = extract_statement(b"fake-pdf-bytes")

        assert not isinstance(result, ExtractionFailure)
        actual_dates = [str(t.transaction_date) for t in result.transactions]
        expected_dates = [expected for _literal, _desc, _amount, expected in self._REAL_STATEMENT_SEQUENCE]
        assert actual_dates == expected_dates

    def test_ccy_conversion_fee_lines_are_excluded_from_correction(self):
        # CCY conversion fee lines are printed grouped separately from the
        # transaction they belong to (not in chronological position), so they're
        # excluded from the positional correction heuristic -- confirmed live: this
        # is the one category the fix doesn't resolve, left to the future-date
        # safety net instead (see TestFutureDatedTransactionFiltering).
        response = {
            "bank_name": "OCBC Bank",
            "currency": "SGD",
            "confidence": "high",
            "transactions": [
                {
                    "transaction_date": "2026-01-13",
                    "description": "-0773 BUS/MRT 779207868",
                    "amount": 1.57,
                    "direction": "out",
                    "printed_converted_amount_sgd": None,
                    "confidence": "high",
                },
                {
                    "transaction_date": "2020-11-01",  # buggy literal for a true "11 Jan" fee line
                    "description": "CCY CONVERSION FEE FOR: 1.48 SGD",
                    "amount": 0.01,
                    "direction": "out",
                    "printed_converted_amount_sgd": None,
                    "confidence": "high",
                },
            ],
        }
        p1, p2 = _mock_pipeline(json.dumps(response))
        with p1, p2:
            result = extract_statement(b"fake-pdf-bytes")

        assert not isinstance(result, ExtractionFailure)
        fee_txn = next(t for t in result.transactions if "CCY CONVERSION" in t.description)
        assert str(fee_txn.transaction_date) == "2020-11-01"  # left untouched, not corrected

    def test_unresolvable_case_would_have_failed_without_the_fix(self):
        # Prove the test actually catches the regression: with the correction pass
        # disabled (simulating pre-fix behaviour), the ambiguous entry keeps its
        # buggy literal date instead of being corrected.
        response = {
            "bank_name": "OCBC Bank",
            "currency": "SGD",
            "confidence": "high",
            "transactions": [
                {
                    "transaction_date": "2026-01-01",
                    "description": "-0773 F'EAST",
                    "amount": 0.50,
                    "direction": "out",
                    "printed_converted_amount_sgd": None,
                    "confidence": "high",
                },
                {
                    "transaction_date": "2026-03-01",
                    "description": "-0773 IKEA-RESTAURANT",
                    "amount": 53.90,
                    "direction": "out",
                    "printed_converted_amount_sgd": None,
                    "confidence": "high",
                },
            ],
        }
        p1, p2 = _mock_pipeline(json.dumps(response))
        with p1, p2, patch(
            "ingestion_worker.extraction.service._correct_ambiguous_transaction_dates",
            side_effect=lambda transactions, raw_statement_date=None: None,
        ):
            result = extract_statement(b"fake-pdf-bytes")

        assert not isinstance(result, ExtractionFailure)
        ikea = next(t for t in result.transactions if "IKEA" in t.description)
        assert str(ikea.transaction_date) == "2026-03-01"  # still buggy, uncorrected


class TestStatementDateAnchoredCorrectionForExcludedLines:
    """Regression coverage for a real, live gap found by re-running the fix above
    through the actual Gemini pipeline against a real statement PDF: excluded
    administrative lines aren't corrected by the sequential heuristic (they aren't
    printed in chronological order), but they're not immune to the same
    ambiguous-date bug either -- a real "PAYMENT BY INTERNET" line ($776.52) came
    back dated 2026-01-03 instead of the correct 2026-03-01. Both real examples
    (this one and the already-correct one in TestAmbiguousDateCorrection) land
    exactly on the statement's own printed statement_date, so that's used as a
    narrow, cross-validated anchor for excluded lines specifically. See
    aidlc-docs/audit.md 2026-08-04."""

    def _response(self, statement_date, transactions):
        return {
            "bank_name": "OCBC Bank",
            "currency": "SGD",
            "statement_date": statement_date,
            "confidence": "high",
            "transactions": transactions,
        }

    def _txn(self, transaction_date, description, amount=10.0):
        return {
            "transaction_date": transaction_date,
            "description": description,
            "amount": amount,
            "direction": "out",
            "printed_converted_amount_sgd": None,
            "confidence": "high",
        }

    def test_misread_payment_line_is_corrected_to_statement_date(self):
        # Real case: statement_date "01-03-2026" (1 March), payment line's raw date
        # came back as 2026-01-03 (day/month swapped) instead of 2026-03-01.
        response = self._response(
            "2026-01-03",  # statement_date itself ALSO came back swapped this run
            [
                self._txn("2026-01-29", "-0773 BUS/MRT 789177623"),  # unambiguous, establishes trust
                self._txn("2026-02-27", "-0773 BUS/MRT 794948924"),  # unambiguous, latest trusted date
                self._txn("2026-01-03", "PAYMENT BY INTERNET", amount=776.52),  # excluded, buggy literal
            ],
        )
        p1, p2 = _mock_pipeline(json.dumps(response))
        with p1, p2:
            result = extract_statement(b"fake-pdf-bytes")

        assert not isinstance(result, ExtractionFailure)
        payment = next(t for t in result.transactions if "PAYMENT" in t.description)
        assert str(payment.transaction_date) == "2026-03-01"

    def test_already_correct_payment_line_is_left_unchanged(self):
        # Real case: statement_date "01-02-2026" (1 Feb), payment line's raw date
        # already correctly came back as 2026-02-01 -- must not be "corrected" away.
        response = self._response(
            "2026-02-01",
            [
                self._txn("2026-01-13", "-0773 ABECHA-FUEL @ ESSO/MOBIL"),  # unambiguous, establishes trust
                self._txn("2026-01-31", "-0773 BUS/MRT 771790695"),  # unambiguous, latest trusted date
                self._txn("2026-02-01", "PAYMENT BY INTERNET", amount=1056.10),  # excluded, already correct
            ],
        )
        p1, p2 = _mock_pipeline(json.dumps(response))
        with p1, p2:
            result = extract_statement(b"fake-pdf-bytes")

        assert not isinstance(result, ExtractionFailure)
        payment = next(t for t in result.transactions if "PAYMENT" in t.description)
        assert str(payment.transaction_date) == "2026-02-01"

    def test_implausible_statement_date_is_not_trusted(self):
        # If the extracted statement_date is nowhere near the statement's own latest
        # unambiguous transaction date (e.g. a wild misread), it must not be used to
        # "correct" an excluded line -- safer to leave it as extracted than to
        # confidently apply a bad anchor.
        response = self._response(
            "2019-06-15",  # implausible: nowhere near the transactions below
            [
                self._txn("2026-01-13", "-0773 ABECHA-FUEL @ ESSO/MOBIL"),
                self._txn("2026-01-31", "-0773 BUS/MRT 771790695"),
                self._txn("2026-01-02", "PAYMENT BY INTERNET", amount=1056.10),
            ],
        )
        p1, p2 = _mock_pipeline(json.dumps(response))
        with p1, p2:
            result = extract_statement(b"fake-pdf-bytes")

        assert not isinstance(result, ExtractionFailure)
        payment = next(t for t in result.transactions if "PAYMENT" in t.description)
        assert str(payment.transaction_date) == "2026-01-02"  # left untouched

    def test_missing_statement_date_leaves_excluded_lines_untouched(self):
        response = self._response(
            None,
            [
                self._txn("2026-01-13", "-0773 ABECHA-FUEL @ ESSO/MOBIL"),
                self._txn("2026-01-03", "PAYMENT BY INTERNET", amount=776.52),
            ],
        )
        p1, p2 = _mock_pipeline(json.dumps(response))
        with p1, p2:
            result = extract_statement(b"fake-pdf-bytes")

        assert not isinstance(result, ExtractionFailure)
        payment = next(t for t in result.transactions if "PAYMENT" in t.description)
        assert str(payment.transaction_date) == "2026-01-03"  # no anchor available, left untouched


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


def _txn(day: str, description: str = "TXN", amount: float = 10.0, direction: str = "out") -> dict:
    return {
        "transaction_date": day,
        "description": description,
        "amount": amount,
        "direction": direction,
        "printed_converted_amount_sgd": None,
        "confidence": "high",
    }


def _sectioned(*sections: dict, **overrides) -> dict:
    return {"bank_name": "DBS", "currency": "SGD", "confidence": "high", "sections": list(sections), **overrides}


def _extract(response: dict):
    p1, p2 = _mock_pipeline(json.dumps(response))
    with p1, p2:
        return extract_statement(b"fake-pdf-bytes")


class TestAccountSections:
    """Epic 13 (WR-44, WR-46): a statement holds one or more account sections."""

    def test_two_sections_are_returned_with_their_own_fields(self):
        result = _extract(
            _sectioned(
                {"account_identifier": "123-456", "account_type": "deposit", "closing_balance": 1000.5,
                 "closing_balance_date": "2026-01-31", "transactions": [_txn("2026-01-15", "A")]},
                {"account_identifier": "4111", "account_type": "credit_card", "closing_balance": None,
                 "transactions": [_txn("2026-01-16", "B")]},
            )
        )

        assert not isinstance(result, ExtractionFailure)
        assert [s.account_identifier for s in result.sections] == ["123-456", "4111"]
        assert [s.account_type.value for s in result.sections] == ["deposit", "credit_card"]
        assert result.sections[0].closing_balance == Decimal("1000.5")
        assert [t.description for t in result.transactions] == ["A", "B"]

    def test_a_flat_reply_still_works_as_one_section(self):
        result = _extract({**_VALID_RESPONSE})

        assert not isinstance(result, ExtractionFailure)
        assert len(result.sections) == 1
        assert result.sections[0].currency == "SGD"

    def test_section_currency_defaults_to_the_statement_currency(self):
        result = _extract(_sectioned({"transactions": [_txn("2026-01-15")]}))

        assert result.sections[0].currency == "SGD"

    def test_a_section_may_have_its_own_currency(self):
        result = _extract(
            _sectioned({"transactions": [_txn("2026-01-15")]}, {"currency": "usd", "transactions": [_txn("2026-01-16")]})
        )

        assert [s.currency for s in result.sections] == ["SGD", "USD"]

    def test_no_currency_anywhere_is_the_existing_failure(self):
        result = _extract(_sectioned({"transactions": [_txn("2026-01-15")]}, currency=None))

        assert isinstance(result, ExtractionFailure)
        assert "bank name and/or currency" in result.reason

    def test_a_section_currency_alone_is_enough_when_the_statement_has_none(self):
        result = _extract(_sectioned({"currency": "SGD", "transactions": [_txn("2026-01-15")]}, currency=None))

        assert not isinstance(result, ExtractionFailure)

    def test_new_fields_never_fail_an_extraction(self):
        result = _extract(
            _sectioned(
                {"account_type": "who knows", "closing_balance": "n/a", "closing_balance_date": "garbage",
                 "account_identifier": None, "transactions": [_txn("2026-01-15")]}
            )
        )

        assert not isinstance(result, ExtractionFailure)
        section = result.sections[0]
        assert section.account_type.value == "unknown"
        assert section.closing_balance is None and section.closing_balance_date is None

    def test_zero_transactions_across_the_whole_statement_is_a_failure(self):
        result = _extract(_sectioned({"transactions": []}, {"transactions": []}))

        assert isinstance(result, ExtractionFailure)
        assert "Zero transactions" in result.reason

    def test_one_section_with_no_transactions_is_fine_if_another_has_some(self):
        result = _extract(
            _sectioned(
                {"account_identifier": "111", "closing_balance": 50.0, "closing_balance_date": "2026-01-31", "transactions": []},
                {"account_identifier": "222", "transactions": [_txn("2026-01-15")]},
            )
        )

        assert not isinstance(result, ExtractionFailure)
        assert [s.account_identifier for s in result.sections] == ["111", "222"]  # the empty one kept: it has a balance

    def test_a_section_with_neither_transactions_nor_a_balance_is_dropped(self):
        result = _extract(_sectioned({"account_identifier": "999", "transactions": []}, {"transactions": [_txn("2026-01-15")]}))

        assert [s.account_identifier for s in result.sections] == [None]

    def test_balance_restatement_lines_are_dropped_in_every_section(self):
        result = _extract(
            _sectioned(
                {"transactions": [_txn("2026-01-15", "BALANCE BROUGHT FORWARD"), _txn("2026-01-16", "COFFEE")]},
                {"transactions": [_txn("2026-01-17", "Closing Balance"), _txn("2026-01-18", "LUNCH")]},
            )
        )

        assert [t.description for t in result.transactions] == ["COFFEE", "LUNCH"]


class TestClosingBalanceValidation:
    """WR-47: the closing date gets the same protection as every other date."""

    def _section(self, **fields) -> dict:
        return {"closing_balance": 500.0, "transactions": [_txn("2026-01-15"), _txn("2026-01-28")], **fields}

    def test_a_date_on_or_shortly_after_the_last_transaction_is_kept(self):
        result = _extract(_sectioned(self._section(closing_balance_date="2026-01-31")))

        assert str(result.sections[0].closing_balance_date) == "2026-01-31"
        assert result.sections[0].closing_balance == Decimal("500.0")

    def test_an_ambiguous_date_is_resolved_to_the_reading_inside_the_window(self):
        # printed 31/01 or 01/02: "2026-02-01" read month-first lands a day-order away; the
        # reading in the window after the 28 Jan transaction is 1 Feb.
        result = _extract(_sectioned(self._section(closing_balance_date="2026-01-02")))

        assert str(result.sections[0].closing_balance_date) == "2026-02-01"

    def test_an_implausible_date_falls_back_to_the_validated_statement_date(self):
        result = _extract(_sectioned(self._section(closing_balance_date="2025-06-30"), statement_date="2026-01-31"))

        assert str(result.sections[0].closing_balance_date) == "2026-01-31"
        assert result.sections[0].closing_balance == Decimal("500.0")

    def test_an_implausible_date_with_no_usable_statement_date_drops_the_pair(self):
        result = _extract(_sectioned(self._section(closing_balance_date="2025-06-30")))

        assert result.sections[0].closing_balance is None
        assert result.sections[0].closing_balance_date is None

    def test_a_balance_with_no_date_uses_the_statement_date(self):
        result = _extract(_sectioned(self._section(closing_balance_date=None), statement_date="2026-01-31"))

        assert str(result.sections[0].closing_balance_date) == "2026-01-31"

    def test_a_date_with_no_balance_is_dropped(self):
        result = _extract(_sectioned(self._section(closing_balance=None, closing_balance_date="2026-01-31")))

        assert result.sections[0].closing_balance is None
        assert result.sections[0].closing_balance_date is None

    def test_the_whole_document_swap_also_repairs_closing_dates(self):
        # transactions printed with day and month transposed for the whole document (the real OCBC failure),
        # and the closing date written the same way
        result = _extract(
            _sectioned(
                {"closing_balance": 12.0, "closing_balance_date": "2026-31-01",
                 "transactions": [_txn("2026-13-01"), _txn("2026-28-01")]}
            )
        )

        assert [str(t.transaction_date) for t in result.transactions] == ["2026-01-13", "2026-01-28"]
        assert str(result.sections[0].closing_balance_date) == "2026-01-31"

    def test_a_lone_odd_closing_date_never_triggers_the_document_swap(self):
        # only the closing date is malformed; the transaction dates are fine and must stay as they are
        result = _extract(
            _sectioned(
                {"closing_balance": 12.0, "closing_balance_date": "2026-31-01",
                 "transactions": [_txn("2026-01-13"), _txn("2026-01-28")]},
                statement_date="2026-01-31",
            )
        )

        assert [str(t.transaction_date) for t in result.transactions] == ["2026-01-13", "2026-01-28"]
        assert str(result.sections[0].closing_balance_date) == "2026-01-31"  # fell back to the statement date


class TestPerSectionDateCorrection:
    """WR-46: the chronological ambiguous-date heuristic restarts at each account section."""

    def test_the_second_sections_sequence_is_not_judged_against_the_first(self):
        # Section 1 ends on 20 Jan; section 2 legitimately restarts at 3 Jan. Judged as ONE list,
        # "2026-01-03" would look like a backwards jump and be "corrected" to 1 March.
        result = _extract(
            _sectioned(
                {"transactions": [_txn("2026-01-02", "A1"), _txn("2026-01-20", "A2")]},
                {"transactions": [_txn("2026-01-03", "B1"), _txn("2026-01-05", "B2")]},
            )
        )

        by_description = {t.description: str(t.transaction_date) for t in result.transactions}
        assert by_description == {"A1": "2026-01-02", "A2": "2026-01-20", "B1": "2026-01-03", "B2": "2026-01-05"}
