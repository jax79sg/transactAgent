"""Internal pipeline DTOs (functional-design/domain-entities.md).

These double as the JSON schema the extraction LLM is asked to conform to, and as
the validation target for its response (WR-1's "structural validation" criterion).

Epic 13 (Account Balance at a Point in Time, WR-44): a statement holds one or more
*account sections*. Everything new is parsed leniently -- an unknown account type,
a malformed closing balance or date, or a missing identifier can never fail
validation (and so can never fail an extraction); it simply degrades to "unknown" or
"absent". A reply that predates the sections shape (a flat `transactions` list) is
accepted and wrapped as one section.
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def rank(self) -> int:
        return {"low": 0, "medium": 1, "high": 2}[self.value]


class Direction(str, Enum):
    IN = "in"
    OUT = "out"


class ExtractedAccountType(str, Enum):
    """Same three values as the Database unit's AccountType (kept separate so this
    module stays a plain pydantic DTO layer); the Account Resolver maps between them."""

    DEPOSIT = "deposit"
    CREDIT_CARD = "credit_card"
    UNKNOWN = "unknown"


class RawExtractedTransaction(BaseModel):
    transaction_date: date
    description: str
    amount: Decimal = Field(gt=0)
    direction: Direction
    printed_converted_amount_sgd: Decimal | None = None
    confidence: ConfidenceLevel


class RawAccountSection(BaseModel):
    account_identifier: str | None = None
    account_type: ExtractedAccountType = ExtractedAccountType.UNKNOWN
    currency: str | None = None
    closing_balance: Decimal | None = None
    closing_balance_date: date | None = None
    transactions: list[RawExtractedTransaction] = Field(default_factory=list)

    @field_validator("account_identifier", mode="before")
    @classmethod
    def _identifier_as_text(cls, value: Any) -> str | None:
        if value is None or isinstance(value, bool):
            return None
        text = str(value).strip()
        return text or None

    @field_validator("account_type", mode="before")
    @classmethod
    def _unknown_type_degrades_to_unknown(cls, value: Any) -> ExtractedAccountType:
        if isinstance(value, ExtractedAccountType):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower().replace(" ", "_").replace("-", "_")
            try:
                return ExtractedAccountType(normalized)
            except ValueError:
                pass
        return ExtractedAccountType.UNKNOWN

    @field_validator("currency", mode="before")
    @classmethod
    def _currency_as_upper_text(cls, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip().upper()
        return text or None

    @field_validator("closing_balance", mode="before")
    @classmethod
    def _malformed_balance_is_absent(cls, value: Any) -> Decimal | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            parsed = value if isinstance(value, Decimal) else Decimal(str(value).replace(",", "").strip())
        except InvalidOperation:
            return None
        return parsed if parsed.is_finite() else None

    @field_validator("closing_balance_date", mode="before")
    @classmethod
    def _malformed_balance_date_is_absent(cls, value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value).strip())
        except ValueError:
            return None


def wrap_flat_reply(data: Any) -> Any:
    """WR-44: a reply with no sections but a flat `transactions` list is treated as one
    implicit section. Returns `data` unchanged if it is not a dict or already has
    sections; never mutates its argument."""
    if not isinstance(data, dict):
        return data
    sections = data.get("sections")
    if sections:
        return data
    if "transactions" in data:
        rest = {k: v for k, v in data.items() if k not in ("transactions", "sections")}
        return {**rest, "sections": [{"transactions": data["transactions"]}]}
    return data


class RawExtractedStatement(BaseModel):
    bank_name: str | None = None
    # The statement's primary currency -- the default for any section that has none.
    currency: str | None = None
    confidence: ConfidenceLevel
    # The date printed on the statement itself (e.g. "Statement Date"), if present.
    # Used as a cross-checked anchor for ambiguous-date correction -- see
    # extraction/service.py's _resolve_statement_date. Never required: WR-2 only
    # gates on bank_name/currency, so a statement missing this field still commits.
    statement_date: date | None = None
    sections: list[RawAccountSection] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _accept_a_flat_reply(cls, data: Any) -> Any:
        return wrap_flat_reply(data)

    @property
    def transactions(self) -> list[RawExtractedTransaction]:
        """Every transaction across every section, in order -- for callers that don't
        care which account a transaction belongs to."""
        return [txn for section in self.sections for txn in section.transactions]
