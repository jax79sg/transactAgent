"""Currency conversion (business-logic-model.md — Currency Conversion Component,
WR-6 source priority). Split into a pure decision function (`resolve_conversion_source`
-- the PBT target) and an outer I/O-performing function (`resolve_converted_amount`).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from ingestion_worker.clients.fx_client import fetch_historical_rate
from ingestion_worker.clients.retry import TransientError
from ingestion_worker.config import settings
from ingestion_worker.currency import repository


@dataclass
class ConversionResult:
    converted_amount_sgd: Decimal | None
    is_approximate: bool
    is_unavailable: bool
    fx_rate_id: str | None = None


def resolve_conversion_source(
    *,
    amount: Decimal,
    currency: str,
    printed_converted_amount_sgd: Decimal | None,
    exact_rate: Decimal | None,
    fallback_rate: Decimal | None,
    reporting_currency: str = "SGD",
) -> tuple[str, Decimal | None, bool]:
    """Pure function: WR-6 priority order, given already-resolved inputs.

    Returns (source, converted_amount, is_approximate). Never touches the database or
    network -- the caller (`resolve_converted_amount`) is responsible for fetching
    `exact_rate` / `fallback_rate` and persisting the fx_rate_cache row.
    """
    if printed_converted_amount_sgd is not None:
        return "statement_printed", printed_converted_amount_sgd, False
    if currency == reporting_currency:
        return "identity_sgd", amount, False
    if exact_rate is not None:
        return "fx_api_exact", (amount * exact_rate).quantize(Decimal("0.01")), False
    if fallback_rate is not None:
        return "fx_api_fallback", (amount * fallback_rate).quantize(Decimal("0.01")), True
    return "unavailable", None, False


def resolve_converted_amount(
    db: Session,
    *,
    amount: Decimal,
    currency: str,
    transaction_date: date,
    printed_converted_amount_sgd: Decimal | None,
) -> ConversionResult:
    reporting_currency = settings.reporting_currency

    if printed_converted_amount_sgd is not None or currency == reporting_currency:
        source, converted, is_approximate = resolve_conversion_source(
            amount=amount,
            currency=currency,
            printed_converted_amount_sgd=printed_converted_amount_sgd,
            exact_rate=None,
            fallback_rate=None,
            reporting_currency=reporting_currency,
        )
        return ConversionResult(converted_amount_sgd=converted, is_approximate=is_approximate, is_unavailable=False)

    cached_exact = repository.find_exact_rate(db, currency, reporting_currency, transaction_date)
    exact_rate = cached_exact.rate if cached_exact else None
    exact_rate_id = str(cached_exact.id) if cached_exact else None

    if exact_rate is None:
        try:
            fetched = fetch_historical_rate(currency, reporting_currency, transaction_date)
        except TransientError:
            fetched = None  # exhausted retries -- fall through to nearest-prior/unavailable
        if fetched is not None:
            row = repository.insert_rate(
                db, from_currency=currency, to_currency=reporting_currency, rate_date=transaction_date, rate=fetched
            )
            exact_rate = row.rate
            exact_rate_id = str(row.id)

    fallback_rate = None
    fallback_rate_id = None
    if exact_rate is None:
        cached_fallback = repository.find_nearest_prior_rate(db, currency, reporting_currency, transaction_date)
        if cached_fallback is not None:
            fallback_rate = cached_fallback.rate
            fallback_rate_id = str(cached_fallback.id)

    source, converted, is_approximate = resolve_conversion_source(
        amount=amount,
        currency=currency,
        printed_converted_amount_sgd=None,
        exact_rate=exact_rate,
        fallback_rate=fallback_rate,
        reporting_currency=reporting_currency,
    )
    rate_id_used = exact_rate_id if source == "fx_api_exact" else (fallback_rate_id if source == "fx_api_fallback" else None)

    return ConversionResult(
        converted_amount_sgd=converted,
        is_approximate=is_approximate,
        is_unavailable=(source == "unavailable"),
        fx_rate_id=rate_id_used,
    )
