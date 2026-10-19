"""Request and response shapes for Account Management (Epic 13, `domain-entities.md`): camelCase JSON, money as exact
two-place strings."""

from datetime import date, datetime
from uuid import UUID

from pydantic import StrictFloat, StrictInt, StrictStr

from api_service.schemas import CamelModel, Money


class AnchorDTO(CamelModel):
    balance: Money
    as_of_date: date
    updated_at: datetime


class AccountDTO(CamelModel):
    id: UUID
    name: str
    bank_name: str
    account_identifier: str | None
    type: str
    type_set_by_user: bool
    currency: str
    anchor: AnchorDTO | None
    can_have_anchor: bool
    statement_count: int
    transaction_count: int
    closing_balance_count: int
    latest_transaction_date: date | None


class AccountListResponse(CamelModel):
    items: list[AccountDTO]


class AccountUpdateRequest(CamelModel):
    """At least one of the two; which fields were sent is read from `model_fields_set` (AR-52). The type is validated
    by the service so that a wrong value is the stable `invalid_account_type` error, not a framework one."""

    name: StrictStr | None = None
    type: StrictStr | None = None


class AnchorRequest(CamelModel):
    """The balance may arrive as a string or a number; the service checks it is a finite decimal with at most two
    places (AR-53)."""

    balance: StrictStr | StrictInt | StrictFloat
    as_of_date: date


class AnchorResponse(CamelModel):
    anchor: AnchorDTO
    previous: AnchorDTO | None


class MergeRequest(CamelModel):
    absorbed_account_id: UUID
    keep_anchor_from: UUID | None = None
