from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session
from transactagent_db.models import FxRateCache


def find_exact_rate(db: Session, from_currency: str, to_currency: str, rate_date: date) -> FxRateCache | None:
    return db.scalar(
        select(FxRateCache).where(
            FxRateCache.from_currency == from_currency,
            FxRateCache.to_currency == to_currency,
            FxRateCache.rate_date == rate_date,
        )
    )


def find_nearest_prior_rate(
    db: Session, from_currency: str, to_currency: str, rate_date: date
) -> FxRateCache | None:
    return db.scalar(
        select(FxRateCache)
        .where(
            FxRateCache.from_currency == from_currency,
            FxRateCache.to_currency == to_currency,
            FxRateCache.rate_date <= rate_date,
        )
        .order_by(FxRateCache.rate_date.desc())
        .limit(1)
    )


def insert_rate(db: Session, *, from_currency: str, to_currency: str, rate_date: date, rate: Decimal) -> FxRateCache:
    row = FxRateCache(from_currency=from_currency, to_currency=to_currency, rate_date=rate_date, rate=rate)
    db.add(row)
    db.flush()
    return row
