"""Response shapes for balances (Epic 13, `domain-entities.md`): camelCase JSON, money as exact two-place strings."""

from datetime import date
from uuid import UUID

from api_service.schemas import CamelModel, Money


class BasisDTO(CamelModel):
    """What a balance was worked from (AR-55)."""

    source: str  # "anchor" | "statement_closing"
    date: date
    statement_id: UUID | None


class AccountBalanceDTO(CamelModel):
    account_id: UUID
    name: str
    bank_name: str
    currency: str
    status: str  # "ok" | "anchor_required" | "fx_unavailable"
    balance_native: Money | None
    balance_sgd: Money | None
    is_approximate: bool
    fx_rate_date: date | None
    basis: BasisDTO | None
    latest_transaction_date: date | None


class ExcludedAccountDTO(CamelModel):
    account_id: UUID
    name: str
    reason: str  # "anchor_required" | "fx_unavailable"


class CurrencyNetDTO(CamelModel):
    currency: str
    net: Money


class UnlinkedNoticeDTO(CamelModel):
    count: int
    bank_names: list[str]
    earliest_date: date
    latest_date: date
    net_by_currency: list[CurrencyNetDTO]


class BalancesResponse(CamelModel):
    resolved_date: date
    today: date
    requested_month: str | None
    ingested_through_date: date | None
    accounts: list[AccountBalanceDTO]
    combined_total_sgd: Money | None
    combined_includes_count: int
    excluded: list[ExcludedAccountDTO]
    has_approximate: bool
    unlinked_transactions: UnlinkedNoticeDTO | None


class SeriesAccountDTO(CamelModel):
    account_id: UUID
    name: str
    currency: str


class SeriesPointDTO(CamelModel):
    date: date
    combined_sgd: Money | None
    per_account: dict[str, Money | None]  # a null is a gap: no usable FX rate for that date (AR-61)
    approximate_account_ids: list[UUID]


class SeriesResponse(CamelModel):
    start: date
    end: date
    granularity: str  # the resolved one: "day" | "month"
    accounts: list[SeriesAccountDTO]
    missing_accounts: list[ExcludedAccountDTO]
    points: list[SeriesPointDTO]


class StatementDifferenceDTO(CamelModel):
    statement_id: UUID | None
    closing_date: date
    printed_balance: Money
    computed_balance: Money
    difference: Money


class PeriodGapDTO(CamelModel):
    from_statement_id: UUID | None
    to_statement_id: UUID | None
    from_date: date
    to_date: date
    printed_change: Money
    transaction_net: Money
    gap: Money


class AccountDiscrepancyDTO(CamelModel):
    account_id: UUID
    name: str
    currency: str
    statements_checked: int
    periods_checked: int
    statement_differences: list[StatementDifferenceDTO]
    period_gaps: list[PeriodGapDTO]


class DiscrepanciesResponse(CamelModel):
    tolerance: Money
    accounts_checked: int
    items: list[AccountDiscrepancyDTO]
