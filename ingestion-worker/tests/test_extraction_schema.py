"""Property-based round-trip test for the extraction response schema (PBT-02:
serialize -> deserialize = identity). WR-1b's structural validation relies on this
schema being a faithful, lossless round-trip for well-formed data."""

from datetime import date
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from ingestion_worker.extraction.schemas import (
    ConfidenceLevel,
    Direction,
    RawExtractedStatement,
    RawExtractedTransaction,
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


def _statement_strategy():
    return st.builds(
        RawExtractedStatement,
        bank_name=st.none() | st.text(min_size=1, max_size=100),
        currency=st.none() | st.sampled_from(["SGD", "USD", "EUR", "MYR"]),
        confidence=_confidence,
        transactions=st.lists(_transaction_strategy(), max_size=10),
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
