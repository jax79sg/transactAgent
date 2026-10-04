"""Property-based round-trip test for the extraction response schema (PBT-02:
serialize -> deserialize = identity). WR-1b's structural validation relies on this
schema being a faithful, lossless round-trip for well-formed data."""

from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ingestion_worker.extraction.schemas import (
    ConfidenceLevel,
    Direction,
    ExtractedAccountType,
    RawAccountSection,
    RawExtractedStatement,
    RawExtractedTransaction,
    wrap_flat_reply,
)

_confidence = st.sampled_from(list(ConfidenceLevel))
_direction = st.sampled_from(list(Direction))
_amount = st.decimals(min_value="0.01", max_value="1000000", places=2).map(Decimal)
_dates = st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 1, 1))


def _transaction_strategy():
    return st.builds(
        RawExtractedTransaction,
        transaction_date=_dates,
        description=st.text(min_size=1, max_size=200),
        amount=_amount,
        direction=_direction,
        printed_converted_amount_sgd=st.none() | _amount,
        confidence=_confidence,
    )


_identifier = st.none() | st.text(alphabet="0123456789XABC*", min_size=1, max_size=20)


def _section_strategy():
    return st.builds(
        RawAccountSection,
        account_identifier=_identifier,
        account_type=st.sampled_from(list(ExtractedAccountType)),
        currency=st.none() | st.sampled_from(["SGD", "USD", "EUR", "MYR"]),
        closing_balance=st.none() | st.decimals(min_value="-1000000", max_value="1000000", places=2),
        closing_balance_date=st.none() | _dates,
        transactions=st.lists(_transaction_strategy(), max_size=5),
    )


def _statement_strategy():
    return st.builds(
        RawExtractedStatement,
        bank_name=st.none() | st.text(min_size=1, max_size=100),
        currency=st.none() | st.sampled_from(["SGD", "USD", "EUR", "MYR"]),
        confidence=_confidence,
        sections=st.lists(_section_strategy(), max_size=3),
    )


class TestExtractionSchemaRoundTrip:
    @given(statement=_statement_strategy())
    def test_json_round_trip_is_lossless(self, statement):
        serialized = statement.model_dump_json()
        deserialized = RawExtractedStatement.model_validate_json(serialized)
        assert deserialized == statement

    @given(statement=_statement_strategy())
    def test_dict_round_trip_is_lossless(self, statement):
        as_dict = statement.model_dump(mode="json")
        rebuilt = RawExtractedStatement.model_validate(as_dict)
        assert rebuilt == statement

    @given(confidence=_confidence)
    def test_confidence_rank_is_monotonic_with_declaration_order(self, confidence):
        ranks = [c.rank for c in ConfidenceLevel]
        assert ranks == sorted(ranks)
        assert confidence.rank in range(len(ConfidenceLevel))


_TXN = {
    "transaction_date": "2026-01-15",
    "description": "NTUC FAIRPRICE",
    "amount": 25.5,
    "direction": "out",
    "printed_converted_amount_sgd": None,
    "confidence": "high",
}


class TestSectionsAreParsedLeniently:
    """WR-44: nothing new can fail validation; it degrades to unknown/absent instead."""

    def test_flat_reply_is_wrapped_as_one_section(self):
        statement = RawExtractedStatement.model_validate(
            {"bank_name": "DBS", "currency": "SGD", "confidence": "high", "transactions": [_TXN]}
        )

        assert len(statement.sections) == 1
        assert [t.description for t in statement.transactions] == ["NTUC FAIRPRICE"]

    def test_wrap_flat_reply_does_not_mutate_its_argument_or_touch_a_sectioned_reply(self):
        flat = {"bank_name": "DBS", "transactions": [_TXN]}
        wrapped = wrap_flat_reply(flat)
        assert "transactions" in flat and "sections" not in flat
        assert wrapped["sections"] == [{"transactions": [_TXN]}]
        sectioned = {"sections": [{"transactions": []}]}
        assert wrap_flat_reply(sectioned) is sectioned
        assert wrap_flat_reply(["not", "a", "dict"]) == ["not", "a", "dict"]

    def test_transactions_property_flattens_every_section_in_order(self):
        statement = RawExtractedStatement.model_validate(
            {
                "confidence": "high",
                "sections": [
                    {"transactions": [{**_TXN, "description": "A"}]},
                    {"transactions": [{**_TXN, "description": "B"}, {**_TXN, "description": "C"}]},
                ],
            }
        )

        assert [t.description for t in statement.transactions] == ["A", "B", "C"]

    @pytest.mark.parametrize("raw", ["savings", "", None, 42, "CREDIT_CARD ", "credit card", "Deposit"])
    def test_account_type_never_fails_validation(self, raw):
        section = RawAccountSection.model_validate({"account_type": raw})
        assert isinstance(section.account_type, ExtractedAccountType)

    def test_account_type_variants_are_recognized(self):
        assert RawAccountSection.model_validate({"account_type": "Credit Card"}).account_type == ExtractedAccountType.CREDIT_CARD
        assert RawAccountSection.model_validate({"account_type": " DEPOSIT "}).account_type == ExtractedAccountType.DEPOSIT
        assert RawAccountSection.model_validate({"account_type": "savings"}).account_type == ExtractedAccountType.UNKNOWN

    @pytest.mark.parametrize("raw", ["abc", "NaN", "Infinity", True, "", [1], {"a": 1}])
    def test_malformed_closing_balance_becomes_absent(self, raw):
        assert RawAccountSection.model_validate({"closing_balance": raw}).closing_balance is None

    @pytest.mark.parametrize(("raw", "expected"), [("1,234.50", Decimal("1234.50")), (1234.5, Decimal("1234.5")), ("-12.00", Decimal("-12.00"))])
    def test_closing_balance_forms_are_read(self, raw, expected):
        assert RawAccountSection.model_validate({"closing_balance": raw}).closing_balance == expected

    @pytest.mark.parametrize("raw", ["2026-31-01", "not a date", "20263101", 5, ""])
    def test_malformed_closing_date_becomes_absent(self, raw):
        assert RawAccountSection.model_validate({"closing_balance_date": raw}).closing_balance_date is None

    def test_compact_iso_date_is_a_valid_date(self):
        # YYYYMMDD is unambiguous ISO 8601 basic format, so it is read, not discarded.
        assert RawAccountSection.model_validate({"closing_balance_date": "20260131"}).closing_balance_date == date(2026, 1, 31)

    def test_identifier_is_kept_as_text_and_blank_means_none(self):
        assert RawAccountSection.model_validate({"account_identifier": 501123456}).account_identifier == "501123456"
        assert RawAccountSection.model_validate({"account_identifier": " 12-34 "}).account_identifier == "12-34"
        assert RawAccountSection.model_validate({"account_identifier": "  "}).account_identifier is None
        assert RawAccountSection.model_validate({"account_identifier": True}).account_identifier is None

    def test_currency_is_upper_cased_and_non_text_is_absent(self):
        assert RawAccountSection.model_validate({"currency": " sgd "}).currency == "SGD"
        assert RawAccountSection.model_validate({"currency": 5}).currency is None
