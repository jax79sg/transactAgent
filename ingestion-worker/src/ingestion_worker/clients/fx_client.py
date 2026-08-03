"""Thin wrapper around exchangerate.host — the FX fallback (Clarification 2b = B),
only called when a statement doesn't print its own SGD-converted amount (WR-6)."""

from datetime import date
from decimal import Decimal

import httpx

from ingestion_worker.clients.retry import TransientError, retry_with_backoff

_BASE_URL = "https://api.exchangerate.host"
_TRANSIENT_STATUS = {429, 500, 502, 503, 504}


@retry_with_backoff()
def fetch_historical_rate(from_currency: str, to_currency: str, rate_date: date) -> Decimal | None:
    """Returns the rate for the exact date, or None if unavailable for that date
    (caller applies the nearest-prior-date fallback per WR-6, not this client)."""
    try:
        response = httpx.get(
            f"{_BASE_URL}/{rate_date.isoformat()}",
            params={"base": from_currency, "symbols": to_currency},
            timeout=10.0,
        )
        if response.status_code in _TRANSIENT_STATUS:
            raise TransientError(f"exchangerate.host transient error (status {response.status_code})")
        response.raise_for_status()
        data = response.json()
        rate = data.get("rates", {}).get(to_currency)
        return Decimal(str(rate)) if rate is not None else None
    except httpx.TimeoutException as exc:
        raise TransientError(f"exchangerate.host timeout: {exc}") from exc
    except httpx.ConnectError as exc:
        raise TransientError(f"exchangerate.host connection error: {exc}") from exc
