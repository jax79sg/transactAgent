"""Balance business logic (Epic 13, AR-55 to AR-62, AR-66): the lookup, the series and the discrepancies. Everything
is computed on request from the database and nothing is stored. The arithmetic is in `calculation.py` (pure); this
module gathers the inputs, converts to SGD, adds up the combined total and words the exclusions."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from api_service.balances import calculation as calc
from api_service.balances import repository
from api_service.balances.calculation import (
    ANCHOR,
    STATEMENT_CLOSING,
    KnownBalance,
    NetFlowIndex,
)
from api_service.balances.repository import ClosingRow, DepositAccountRow
from api_service.balances.schemas import (
    AccountBalanceDTO,
    AccountDiscrepancyDTO,
    BalancesResponse,
    BasisDTO,
    CurrencyNetDTO,
    DiscrepanciesResponse,
    ExcludedAccountDTO,
    PeriodGapDTO,
    SeriesAccountDTO,
    SeriesPointDTO,
    SeriesResponse,
    StatementDifferenceDTO,
    UnlinkedNoticeDTO,
)
from api_service.config import settings
from api_service.errors import (
    ApiError,
    DateInFutureError,
    DateOrMonthRequiredError,
    InvalidDateRangeError,
    MonthInFutureError,
    RangeTooLargeError,
)

REPORTING_CURRENCY = "SGD"  # FR-AB-9 fixes it; the worker's `reporting_currency` setting does not change this
STATUS_OK = "ok"
STATUS_ANCHOR_REQUIRED = "anchor_required"
STATUS_FX_UNAVAILABLE = "fx_unavailable"

_ERRORS: dict[str, type[ApiError]] = {
    "date_in_future": DateInFutureError,
    "month_in_future": MonthInFutureError,
    "invalid_date_range": InvalidDateRangeError,
    "range_too_large": RangeTooLargeError,
    "date_or_month_required": DateOrMonthRequiredError,
}


def today_in_reporting_zone(now: datetime | None = None) -> date:
    """AR-57: today's date in the `reporting_time_zone` setting (default Asia/Singapore)."""
    return (now or datetime.now(UTC)).astimezone(ZoneInfo(settings.reporting_time_zone)).date()


def _translate(exc: calc.CalculationError) -> ApiError:
    return _ERRORS.get(exc.code, ApiError)(str(exc))


def known_balances(account: DepositAccountRow, closings: list[ClosingRow]) -> list[KnownBalance]:
    """AR-55: the anchor and the printed closing balances of an account that has an anchor."""
    known = [KnownBalance(account.anchor_balance, account.anchor_date, ANCHOR)]
    known += [
        KnownBalance(c.balance, c.closing_date, STATEMENT_CLOSING, c.statement_id, c.recorded_order) for c in closings
    ]
    return known


def _basis(reference: KnownBalance) -> BasisDTO:
    return BasisDTO(source=reference.source, date=reference.date, statement_id=reference.statement_id)


def _convert(db: Session, currency: str, native: Decimal, on_date: date) -> tuple[Decimal | None, bool, date | None]:
    """AR-59: (SGD amount, approximate, rate date). None for the amount when no usable cached rate exists."""
    if currency == REPORTING_CURRENCY:
        return native, False, None
    found = repository.nearest_earlier_rate(db, currency, on_date)
    if found is None:
        return None, False, None
    rate, rate_date = found
    return calc.to_sgd(native, rate), rate_date != on_date, rate_date


def _excluded(account: DepositAccountRow, reason: str) -> ExcludedAccountDTO:
    return ExcludedAccountDTO(account_id=account.id, name=account.name, reason=reason)


# ----------------------------------------------------------------------------------------------------- the lookup


def get_balances(
    db: Session, *, on_date: date | None = None, month: str | None = None, today: date | None = None
) -> BalancesResponse:
    """AR-57, AR-58: each deposit account's end-of-day balance on one date, and the combined total."""
    today = today or today_in_reporting_zone()
    if (on_date is None) == (month is None):
        raise DateOrMonthRequiredError("Give exactly one of a date or a month")
    try:
        resolved = calc.resolve_month(month, today) if month is not None else calc.validate_lookup_date(on_date, today)
    except calc.CalculationError as exc:
        raise _translate(exc) from exc

    accounts = repository.list_deposit_accounts(db)
    with_anchor = [a for a in accounts if a.anchor_balance is not None]
    closings = repository.list_closing_balances(db, [a.id for a in with_anchor])
    latest_by_account = repository.latest_transaction_dates_by_account(db, [a.id for a in accounts])

    balances: list[AccountBalanceDTO] = []
    excluded: list[ExcludedAccountDTO] = []
    total = Decimal(0)
    included = 0
    for account in accounts:
        common = {
            "account_id": account.id,
            "name": account.name,
            "bank_name": account.bank_name,
            "currency": account.currency,
            "latest_transaction_date": latest_by_account.get(account.id),
        }
        if account.anchor_balance is None:
            balances.append(
                AccountBalanceDTO(**common, status=STATUS_ANCHOR_REQUIRED, balance_native=None, balance_sgd=None,
                                  is_approximate=False, fx_rate_date=None, basis=None)
            )
            excluded.append(_excluded(account, STATUS_ANCHOR_REQUIRED))
            continue

        native, reference = calc.balance_on_date(
            known_balances(account, closings.get(account.id, [])),
            resolved,
            lambda after, through, account_id=account.id: repository.net_flow_between(db, account_id, after, through),
        )
        sgd, approximate, rate_date = _convert(db, account.currency, native, resolved)
        if sgd is None:
            balances.append(
                AccountBalanceDTO(**common, status=STATUS_FX_UNAVAILABLE, balance_native=native, balance_sgd=None,
                                  is_approximate=False, fx_rate_date=None, basis=_basis(reference))
            )
            excluded.append(_excluded(account, STATUS_FX_UNAVAILABLE))
            continue
        balances.append(
            AccountBalanceDTO(**common, status=STATUS_OK, balance_native=native, balance_sgd=sgd,
                              is_approximate=approximate, fx_rate_date=rate_date, basis=_basis(reference))
        )
        total += sgd
        included += 1

    unlinked = repository.unlinked_summary(db)
    return BalancesResponse(
        resolved_date=resolved,
        today=today,
        requested_month=month,
        ingested_through_date=repository.latest_transaction_date_overall(db),
        accounts=balances,
        combined_total_sgd=total if included else None,
        combined_includes_count=included,
        excluded=excluded,
        has_approximate=any(b.is_approximate for b in balances),
        unlinked_transactions=UnlinkedNoticeDTO(
            count=unlinked.count,
            bank_names=unlinked.bank_names,
            earliest_date=unlinked.earliest_date,
            latest_date=unlinked.latest_date,
            net_by_currency=[CurrencyNetDTO(currency=c, net=n) for c, n in unlinked.net_by_currency],
        )
        if unlinked
        else None,
    )


# ---------------------------------------------------------------------------------------------------- the series


def get_series(
    db: Session,
    *,
    start: date | None = None,
    end: date | None = None,
    granularity: str = calc.AUTO,
    today: date | None = None,
) -> SeriesResponse:
    """AR-61: the balance on each plotted date, every point exactly what the lookup returns for that date."""
    today = today or today_in_reporting_zone()
    default_start, default_end = calc.default_series_range(today)
    start, end = start or default_start, end or default_end
    try:
        granularity = calc.resolve_granularity(start, end, granularity)
        dates = calc.validate_series_range(start, end, today, granularity)
    except calc.CalculationError as exc:
        raise _translate(exc) from exc

    accounts = repository.list_deposit_accounts(db)
    plotted = [a for a in accounts if a.anchor_balance is not None]
    missing = [_excluded(a, STATUS_ANCHOR_REQUIRED) for a in accounts if a.anchor_balance is None]
    if not plotted:
        return SeriesResponse(start=start, end=end, granularity=granularity, accounts=[], missing_accounts=missing, points=[])

    closings = repository.list_closing_balances(db, [a.id for a in plotted])
    totals = repository.daily_flow_totals(db, [a.id for a in plotted])
    indexes = {a.id: NetFlowIndex(totals[a.id]) for a in plotted}
    known = {a.id: known_balances(a, closings.get(a.id, [])) for a in plotted}

    points: list[SeriesPointDTO] = []
    for day in dates:
        per_account: dict[str, Decimal | None] = {}
        approximate: list[UUID] = []
        combined = Decimal(0)
        included = 0
        for account in plotted:
            native, _ = calc.balance_on_date(known[account.id], day, indexes[account.id].net)
            sgd, is_approximate, _rate_date = _convert(db, account.currency, native, day)
            per_account[str(account.id)] = sgd
            if sgd is not None:
                combined += sgd
                included += 1
                if is_approximate:
                    approximate.append(account.id)
        points.append(
            SeriesPointDTO(
                date=day, combined_sgd=combined if included else None, per_account=per_account, approximate_account_ids=approximate
            )
        )
    return SeriesResponse(
        start=start,
        end=end,
        granularity=granularity,
        accounts=[SeriesAccountDTO(account_id=a.id, name=a.name, currency=a.currency) for a in plotted],
        missing_accounts=missing,
        points=points,
    )


# ------------------------------------------------------------------------------------------------ discrepancies


def get_discrepancies(db: Session) -> DiscrepanciesResponse:
    """AR-62: statement differences (against the anchor alone) and period gaps, for accounts that have an anchor."""
    tolerance = Decimal(settings.balance_mismatch_tolerance)
    accounts = [a for a in repository.list_deposit_accounts(db) if a.anchor_balance is not None]
    closings = repository.list_closing_balances(db, [a.id for a in accounts])
    totals = repository.daily_flow_totals(db, [a.id for a in accounts])

    items: list[AccountDiscrepancyDTO] = []
    checked = 0
    for account in accounts:
        printed = [
            KnownBalance(c.balance, c.closing_date, STATEMENT_CLOSING, c.statement_id, c.recorded_order)
            for c in closings.get(account.id, [])
        ]
        distinct = calc.deduplicate_by_date(printed)
        if not distinct:
            continue
        checked += 1
        net = NetFlowIndex(totals[account.id]).net
        anchor = KnownBalance(account.anchor_balance, account.anchor_date, ANCHOR)
        differences = calc.statement_differences(anchor, printed, net, tolerance)
        gaps = calc.period_gaps(printed, net, tolerance)
        if differences or gaps:
            items.append(
                AccountDiscrepancyDTO(
                    account_id=account.id,
                    name=account.name,
                    currency=account.currency,
                    statements_checked=len(distinct),
                    periods_checked=len(distinct) - 1,
                    statement_differences=[
                        StatementDifferenceDTO(
                            statement_id=d.statement_id, closing_date=d.closing_date, printed_balance=d.printed_balance,
                            computed_balance=d.computed_balance, difference=d.difference,
                        )
                        for d in differences
                    ],
                    period_gaps=[
                        PeriodGapDTO(
                            from_statement_id=g.from_statement_id, to_statement_id=g.to_statement_id, from_date=g.from_date,
                            to_date=g.to_date, printed_change=g.printed_change, transaction_net=g.transaction_net, gap=g.gap,
                        )
                        for g in gaps
                    ],
                )
            )
    return DiscrepanciesResponse(tolerance=tolerance, accounts_checked=checked, items=items)
