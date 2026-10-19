"""Account Management business logic (Epic 13, AR-51 to AR-54, AR-64, AR-65). Each action is one request and so one
database transaction (the session-per-request commit in `get_db`): any error raised here rolls everything back."""

from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy.orm import Session
from transactagent_db.models import AccountType

from api_service.accounts import repository
from api_service.accounts.repository import AccountListRow
from api_service.accounts.schemas import (
    AccountDTO,
    AccountListResponse,
    AccountUpdateRequest,
    AnchorDTO,
    AnchorRequest,
    AnchorResponse,
    MergeRequest,
)
from api_service.balances.calculation import EARLIEST_DATE
from api_service.balances.service import today_in_reporting_zone
from api_service.errors import (
    AccountNotFoundError,
    AnchorDateInFutureError,
    AnchorDateOutOfRangeError,
    InvalidAccountNameError,
    InvalidAccountTypeError,
    InvalidAnchorValueError,
    MergeAnchorChoiceInvalidError,
    MergeAnchorChoiceRequiredError,
    MergeAppearTogetherError,
    MergeCurrencyMismatchError,
    MergeSameAccountError,
    NotADepositAccountError,
    NothingToChangeError,
)

MAX_NAME_LENGTH = 255
MONEY_LIMIT = Decimal(10) ** 16  # the stored type is NUMERIC(18, 2)
_TYPE_ORDER = {AccountType.DEPOSIT: 0, AccountType.CREDIT_CARD: 1, AccountType.UNKNOWN: 2}


def _dto(row: AccountListRow) -> AccountDTO:
    account = row.account
    return AccountDTO(
        id=account.id,
        name=account.name,
        bank_name=account.bank_name,
        account_identifier=row.account_identifier,
        type=account.account_type.value,
        type_set_by_user=account.type_user_set,
        currency=account.currency,
        anchor=AnchorDTO.model_validate(row.anchor) if row.anchor else None,
        can_have_anchor=account.account_type == AccountType.DEPOSIT,
        statement_count=row.statement_count,
        transaction_count=row.transaction_count,
        closing_balance_count=row.closing_balance_count,
        latest_transaction_date=row.latest_transaction_date,
    )


def _dto_for(db: Session, account_id: UUID) -> AccountDTO:
    row = repository.get_account_row(db, account_id)
    if row is None:  # cannot happen inside the action that has just touched the account
        raise AccountNotFoundError(f"Account {account_id} not found")
    return _dto(row)


def _locked(db: Session, account_id: UUID):
    account = repository.lock_accounts(db, [account_id]).get(account_id)
    if account is None:
        raise AccountNotFoundError(f"Account {account_id} not found")
    return account


def list_accounts(db: Session) -> AccountListResponse:
    """AR-51: deposit accounts first, then credit cards, then unknown; by name (case-insensitively) within each."""
    rows = sorted(
        repository.list_account_rows(db),
        key=lambda r: (_TYPE_ORDER[r.account.account_type], r.account.name.lower(), str(r.account.id)),
    )
    return AccountListResponse(items=[_dto(r) for r in rows])


def update_account(db: Session, account_id: UUID, request: AccountUpdateRequest) -> AccountDTO:
    """AR-52: rename and/or retype. A type change sets the user-set flag; the anchor row is left alone."""
    account = _locked(db, account_id)
    sent = request.model_fields_set & {"name", "type"}
    if not sent:
        raise NothingToChangeError("Name a new name or a new type to change")

    changed = False
    if "name" in sent:
        name = (request.name or "").strip()
        if not 1 <= len(name) <= MAX_NAME_LENGTH:
            raise InvalidAccountNameError(f"A name must be 1 to {MAX_NAME_LENGTH} characters")
        if name != account.name:
            account.name = name
            changed = True
    if "type" in sent:
        try:
            new_type = AccountType(request.type)
        except ValueError:
            raise InvalidAccountTypeError("The type must be deposit, credit_card or unknown") from None
        if new_type != account.account_type:
            account.account_type = new_type
            account.type_user_set = True
            changed = True
    if not changed:
        raise NothingToChangeError("That is already the account's name and type")
    db.flush()
    return _dto_for(db, account_id)


def _parse_balance(value) -> Decimal:
    try:
        balance = Decimal(str(value).strip())
    except InvalidOperation:
        raise InvalidAnchorValueError("The balance is not a number") from None
    if not balance.is_finite():
        raise InvalidAnchorValueError("The balance is not a number")
    if -balance.as_tuple().exponent > 2:
        raise InvalidAnchorValueError("The balance can have at most two decimal places")
    if abs(balance) >= MONEY_LIMIT:
        raise InvalidAnchorValueError("The balance is too large")
    return balance


def set_anchor(db: Session, account_id: UUID, request: AnchorRequest, today: date | None = None) -> AnchorResponse:
    """AR-53: set or replace the account's one anchor (the end-of-day balance of its as-of date)."""
    account = _locked(db, account_id)
    if account.account_type != AccountType.DEPOSIT:
        raise NotADepositAccountError(f"Only a deposit account can have an anchor; this one is {account.account_type.value}")
    balance = _parse_balance(request.balance)
    if request.as_of_date < EARLIEST_DATE:
        raise AnchorDateOutOfRangeError(f"The date cannot be before {EARLIEST_DATE.isoformat()}")
    if request.as_of_date > (today or today_in_reporting_zone()):
        raise AnchorDateInFutureError("The date cannot be in the future")

    existing = repository.get_anchor(db, account_id)
    previous = AnchorDTO.model_validate(existing) if existing else None  # copied before the write replaces it
    anchor = repository.upsert_anchor(db, account_id, balance, request.as_of_date)
    return AnchorResponse(anchor=AnchorDTO.model_validate(anchor), previous=previous)


def merge_accounts(db: Session, surviving_id: UUID, request: MergeRequest) -> AccountDTO:
    """AR-54: merge `absorbed_account_id` into the surviving account, all or nothing."""
    absorbed_id, keep = request.absorbed_account_id, request.keep_anchor_from
    locked = repository.lock_accounts(db, [surviving_id, absorbed_id])
    for needed in (surviving_id, absorbed_id):
        if needed not in locked:
            raise AccountNotFoundError(f"Account {needed} not found")
    if surviving_id == absorbed_id:
        raise MergeSameAccountError("An account cannot be merged into itself")
    survivor, absorbed = locked[surviving_id], locked[absorbed_id]

    if survivor.currency != absorbed.currency:
        raise MergeCurrencyMismatchError(
            f"These accounts are in different currencies ({survivor.currency} and {absorbed.currency}); an account has one currency"
        )
    if repository.statement_lists_both(db, surviving_id, absorbed_id):
        raise MergeAppearTogetherError("A statement lists both accounts, which shows they are different accounts")

    survivor_anchor = repository.get_anchor(db, surviving_id)
    absorbed_anchor = repository.get_anchor(db, absorbed_id)
    if survivor_anchor and absorbed_anchor:
        if keep is None:
            raise MergeAnchorChoiceRequiredError("Both accounts have an anchor; choose which one to keep")
        if keep not in (surviving_id, absorbed_id):
            raise MergeAnchorChoiceInvalidError("The anchor to keep must be one of the two accounts")
        kept = keep
    elif survivor_anchor or absorbed_anchor:
        kept = surviving_id if survivor_anchor else absorbed_id
        if keep is not None and keep != kept:
            raise MergeAnchorChoiceInvalidError("The account named for the anchor has none")
    else:
        kept = None
        if keep is not None:
            raise MergeAnchorChoiceInvalidError("Neither account has an anchor to keep")

    repository.repoint_sections(db, absorbed_id, surviving_id)
    repository.repoint_keys(db, absorbed_id, surviving_id)
    if kept == absorbed_id:
        repository.delete_anchor(db, surviving_id)
        repository.move_anchor(db, absorbed_id, surviving_id)
    else:
        repository.delete_anchor(db, absorbed_id)
    if not survivor.type_user_set and absorbed.type_user_set:
        survivor.account_type = absorbed.account_type
        survivor.type_user_set = True
    db.flush()
    repository.delete_account(db, absorbed_id)
    db.expire_all()
    return _dto_for(db, surviving_id)
