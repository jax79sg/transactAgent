"""Internal pipeline DTOs (functional-design/domain-entities.md).

These double as the JSON schema the extraction LLM is asked to conform to, and as
the validation target for its response (WR-1's "structural validation" criterion).
"""

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


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


class RawExtractedTransaction(BaseModel):
    transaction_date: date
    description: str
    amount: Decimal = Field(gt=0)
    direction: Direction
    printed_converted_amount_sgd: Decimal | None = None
    confidence: ConfidenceLevel


class RawExtractedStatement(BaseModel):
    bank_name: str | None = None
    currency: str | None = None
    confidence: ConfidenceLevel
    # The date printed on the statement itself (e.g. "Statement Date"), if present.
    # Used as a cross-checked anchor for ambiguous-date correction -- see
    # extraction/service.py's _resolve_statement_date. Never required: WR-2 only
    # gates on bank_name/currency, so a statement missing this field still commits.
    statement_date: date | None = None
    transactions: list[RawExtractedTransaction] = Field(default_factory=list)
