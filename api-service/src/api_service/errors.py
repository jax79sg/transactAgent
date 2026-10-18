"""Typed business-rule exceptions and their mapping to the consistent ErrorResponse shape.

Each exception here corresponds to one of the AR-1..AR-10 business rules in
aidlc-docs/construction/api-service/functional-design/business-rules.md.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """Base class for all typed business-rule violations."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    error_code: str = "bad_request"

    def __init__(self, message: str, details: dict | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class UnauthorizedError(ApiError):
    """AR-1: missing/invalid/expired JWT."""

    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "unauthorized"


class InactiveCategoryError(ApiError):
    """AR-2: cannot assign an inactive category."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "inactive_category"


class ReservedCategoryError(ApiError):
    """AR-3: cannot rename/remove the reserved UNSURE category."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "reserved_category"


class DuplicateCategoryNameError(ApiError):
    """AR-4: category name already exists."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "duplicate_category_name"


class CategoryInUseError(ApiError):
    """AR-5: cannot remove a category still referenced by transactions."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "category_in_use"


class IngestionRunAlreadyActiveError(ApiError):
    """AR-6: an ingestion run is already queued or running."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "ingestion_run_already_active"


class RunNotCancellableError(ApiError):
    """A run can only be cancelled while queued or running -- it's already reached
    a terminal status (completed/failed/cancelled)."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "run_not_cancellable"


class CategoryNotFoundError(ApiError):
    """AR-7: correction target category does not exist."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "category_not_found"


class InvalidCurrencyError(ApiError):
    """AR-9: unrecognized ISO 4217 currency code."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "invalid_currency"


class NotFoundError(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "not_found"


class InvalidDateRangeError(ApiError):
    """Ask AI: date_from is after date_to, or a range wasn't given when required."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "invalid_date_range"


class InvalidTimeZoneError(ApiError):
    """Costs page: the time zone name sent with the request is not a known IANA zone."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "invalid_time_zone"


class NoTransactionsInScopeError(ApiError):
    """Ask AI: nothing in the selected scope to ground an answer in."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "no_transactions_in_scope"


class AiServiceUnavailableError(ApiError):
    """Ask AI: the Gemini call failed (network/API error) -- distinct from a 400/404
    since this is a transient upstream failure, not a bad request."""

    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "ai_service_unavailable"


class ProposalNotPendingError(ApiError):
    """AR-12 (Epic 6): a recategorization proposal can only be approved/rejected while
    status='pending' (BR-16, Unit 1) -- surfaced here rather than only relying on the
    DB layer, since there's no DB constraint enforcing single-resolution the way BR-14's
    partial index enforces no-duplicate-pending."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "proposal_not_pending"


class MatchNotPendingError(ApiError):
    """AR-17 (Epic 8): a recurring-payment match can only be approved/rejected while
    status='pending' (BR-23, Unit 1) -- same reasoning as ProposalNotPendingError."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "match_not_pending"


class InvalidRecurringPaymentError(ApiError):
    """Epic 8: surfaces BR-19 (annual requires due_month, monthly must not have
    one) / BR-20 (due_day 1-31) / an unrecognized frequency value cleanly, rather
    than a raw DB CHECK-constraint error -- same reasoning as InactiveCategoryError
    surfacing BR-6 at this layer."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "invalid_recurring_payment"


class DetectionSuggestionNotNewError(ApiError):
    """AR-20 (Epic 8): a detection suggestion can only be dismissed or added while
    status='new'."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "detection_suggestion_not_new"


class DisagreementNotPendingError(ApiError):
    """AR-23 (Matching Precision Refinement): a categorization disagreement can only
    be resolved/rejected while status='pending' (Database BR-27) -- same reasoning as
    ProposalNotPendingError/MatchNotPendingError."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "disagreement_not_pending"


class InvalidResolutionCategoryError(ApiError):
    """AR-24 (Matching Precision Refinement): a disagreement resolution's
    chosenCategoryId must equal one of the two offered candidates (similarity_category_id
    or llm_category_id) -- enforced here as an API contract, not just a UI convention."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "invalid_resolution_category"


class UnknownSettingError(ApiError):
    """AR-28 (Configurable Application Settings): the name isn't on the static
    allow-list -- indistinguishable whether it's genuinely unknown or one of the 13
    excluded secrets (NFR-CAS-2), by design."""

    status_code = status.HTTP_404_NOT_FOUND
    error_code = "unknown_setting"


class InvalidSettingValueError(ApiError):
    """AR-28/AR-29 (Configurable Application Settings): the proposed value fails its
    type/range check, or would break a cross-field constraint with a sibling
    setting."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "invalid_setting_value"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error_code, "message": exc.message, "details": exc.details},
        )


class PairNotPendingError(ApiError):
    """AR-43/AR-42 (Epic 14): a probable-duplicate pair can only be decided while it is `pending`."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "pair_not_pending"


class RemovalNotOfferedError(ApiError):
    """AR-42 (Epic 14, Question 1 = C): removal is offered only for pairs of comparable size; the
    worker stores `removal_allowed` on the pair and the API never overrides it."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "removal_not_offered"


class RemovalAlreadyRequestedError(ApiError):
    """AR-42/AR-43 (Epic 14, BR-45): a removal for this pair is already queued, running, or cleaning up."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "removal_already_requested"


class StatementMissingError(ApiError):
    """AR-42 (Epic 14): one of the pair's statements no longer exists, so there is nothing safe to remove."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "statement_missing"


class ConfirmationOutOfDateError(ApiError):
    """AR-42 (Epic 14): what the user confirmed (which copy, how many manual corrections would be lost)
    no longer matches the data. Nothing was changed; the user must look again."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "confirmation_out_of_date"


class NotASkippedFileError(ApiError):
    """AR-44 (Epic 14): the comparison has no remembered file to override (it belongs to a held pair)."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "not_a_skipped_file"



# --- Epic 13 (Account Balance at a Point in Time): Account Management and Balance, AR-52 to AR-64 ---


class AccountNotFoundError(ApiError):
    """AR-64 (Epic 13): no account has this id."""

    status_code = status.HTTP_404_NOT_FOUND
    error_code = "account_not_found"


class InvalidAnchorValueError(ApiError):
    """AR-53 (Epic 13): the anchor balance is not a finite decimal with at most two places, or is outside the stored money range."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "invalid_anchor_value"


class AnchorDateInFutureError(ApiError):
    """AR-53 (Epic 13): the anchor's as-of date is after today in the reporting time zone."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "anchor_date_in_future"


class AnchorDateOutOfRangeError(ApiError):
    """AR-53 (Epic 13): the anchor's as-of date is before 2000-01-01."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "anchor_date_out_of_range"


class NotADepositAccountError(ApiError):
    """AR-53 (Epic 13): only a deposit account can have an anchor."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "not_a_deposit_account"


class NothingToChangeError(ApiError):
    """AR-52 (Epic 13): an account update that names no field, or changes nothing."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "nothing_to_change"


class InvalidAccountNameError(ApiError):
    """AR-52 (Epic 13): a name must be 1 to 255 characters once trimmed."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "invalid_account_name"


class InvalidAccountTypeError(ApiError):
    """AR-52 (Epic 13): a type must be deposit, credit_card or unknown."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "invalid_account_type"


class MergeSameAccountError(ApiError):
    """AR-54 (Epic 13): an account cannot be merged into itself."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "merge_same_account"


class MergeCurrencyMismatchError(ApiError):
    """AR-54 (Epic 13, A-6): an account has a single currency, so accounts in different currencies cannot be merged."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "merge_currency_mismatch"


class MergeAppearTogetherError(ApiError):
    """AR-54 (Epic 13): a statement that lists both accounts proves they are different accounts."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "merge_appear_together"


class MergeAnchorChoiceRequiredError(ApiError):
    """AR-54 (Epic 13): both accounts have an anchor and the request does not say which to keep."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "merge_anchor_choice_required"


class MergeAnchorChoiceInvalidError(ApiError):
    """AR-54 (Epic 13): the named anchor to keep is not one of the two accounts, or names an account that has none."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "merge_anchor_choice_invalid"


class DateOrMonthRequiredError(ApiError):
    """AR-57 (Epic 13): a balance lookup takes exactly one of a date or a month."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "date_or_month_required"


class DateInFutureError(ApiError):
    """AR-57 (Epic 13): a balance lookup date is after today in the reporting time zone."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "date_in_future"


class MonthInFutureError(ApiError):
    """AR-57 (Epic 13): a balance lookup month is after the current month."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "month_in_future"


class RangeTooLargeError(ApiError):
    """AR-61 (Epic 13): a balance series would have more than 1,500 points."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "range_too_large"
