"""Property-based tests for the pure currency-conversion source-priority resolver (WR-6)."""

from decimal import Decimal

from hypothesis import assume, given
from hypothesis import strategies as st

from ingestion_worker.currency.service import resolve_conversion_source

_amounts = st.decimals(min_value="0.01", max_value="1000000", places=2).map(Decimal)
_rates = st.decimals(min_value="0.0001", max_value="100", places=4).map(Decimal)
_currencies = st.sampled_from(["USD", "EUR", "GBP", "JPY", "MYR"])


class TestResolveConversionSourceProperties:
    @given(amount=_amounts, currency=_currencies, printed=st.none() | _amounts)
    def test_printed_amount_always_wins_when_present(self, amount, currency, printed):
        source, converted, is_approximate = resolve_conversion_source(
            amount=amount,
            currency=currency,
            printed_converted_amount_sgd=printed,
            exact_rate=Decimal("1.5"),
            fallback_rate=Decimal("1.4"),
        )
        if printed is not None:
            assert source == "statement_printed"
            assert converted == printed
            assert is_approximate is False

    @given(amount=_amounts, exact_rate=_rates, fallback_rate=_rates)
    def test_sgd_currency_is_identity_regardless_of_rates(self, amount, exact_rate, fallback_rate):
        source, converted, is_approximate = resolve_conversion_source(
            amount=amount,
            currency="SGD",
            printed_converted_amount_sgd=None,
            exact_rate=exact_rate,
            fallback_rate=fallback_rate,
        )
        assert source == "identity_sgd"
        assert converted == amount
        assert is_approximate is False

    @given(amount=_amounts, currency=_currencies, exact_rate=_rates, fallback_rate=_rates)
    def test_exact_rate_preferred_over_fallback(self, amount, currency, exact_rate, fallback_rate):
        source, converted, is_approximate = resolve_conversion_source(
            amount=amount,
            currency=currency,
            printed_converted_amount_sgd=None,
            exact_rate=exact_rate,
            fallback_rate=fallback_rate,
        )
        assert source == "fx_api_exact"
        assert converted == (amount * exact_rate).quantize(Decimal("0.01"))
        assert is_approximate is False

    @given(amount=_amounts, currency=_currencies, fallback_rate=_rates)
    def test_fallback_rate_used_and_marked_approximate_when_no_exact_rate(self, amount, currency, fallback_rate):
        assume(currency != "SGD")
        source, converted, is_approximate = resolve_conversion_source(
            amount=amount,
            currency=currency,
            printed_converted_amount_sgd=None,
            exact_rate=None,
            fallback_rate=fallback_rate,
        )
        assert source == "fx_api_fallback"
        assert converted == (amount * fallback_rate).quantize(Decimal("0.01"))
        assert is_approximate is True

    @given(amount=_amounts, currency=_currencies)
    def test_unavailable_when_nothing_resolves(self, amount, currency):
        assume(currency != "SGD")
        source, converted, is_approximate = resolve_conversion_source(
            amount=amount, currency=currency, printed_converted_amount_sgd=None, exact_rate=None, fallback_rate=None
        )
        assert source == "unavailable"
        assert converted is None
        assert is_approximate is False

    @given(amount=_amounts, currency=_currencies, exact_rate=_rates, fallback_rate=_rates, printed=_amounts)
    def test_priority_order_is_total_and_deterministic(self, amount, currency, exact_rate, fallback_rate, printed):
        """Calling twice with identical inputs always yields identical output (no hidden state)."""
        args = dict(
            amount=amount,
            currency=currency,
            printed_converted_amount_sgd=printed,
            exact_rate=exact_rate,
            fallback_rate=fallback_rate,
        )
        assert resolve_conversion_source(**args) == resolve_conversion_source(**args)
