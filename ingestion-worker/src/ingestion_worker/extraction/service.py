"""Statement extraction orchestration (business-logic-model.md — Statement Extraction
Component). Implements WR-1 (extraction failure criteria) and WR-2 (bank/currency
required to commit).
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta

import pydantic
from pdf2image import convert_from_bytes

from ingestion_worker.clients.gemini_client import extract_statement_raw
from ingestion_worker.clients.retry import TransientError
from ingestion_worker.config import settings
from ingestion_worker.extraction.prompts import EXTRACTION_PROMPT
from ingestion_worker.extraction.schemas import ConfidenceLevel, RawExtractedStatement

logger = logging.getLogger(__name__)


@dataclass
class ExtractionFailure:
    reason: str
    raw_response: str | None = None


def _pdf_to_page_images(pdf_bytes: bytes) -> list[bytes]:
    images = convert_from_bytes(pdf_bytes, fmt="png")
    page_bytes = []
    for img in images:
        import io

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        page_bytes.append(buf.getvalue())
    return page_bytes


def _parse_llm_json(raw_text: str) -> dict:
    """Gemini sometimes wraps JSON in markdown code fences; strip them if present."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[len("json") :]
    return json.loads(text.strip())


def _statement_needs_day_month_swap(parsed: dict) -> bool:
    """True if at least one transaction_date has a month component >12 (unambiguously
    invalid) that would become a valid month (<=12) if swapped with the day component.

    Many Singapore-issued statements (observed: OCBC) print dates day-first
    (DD/MM/YY); Gemini has been observed to correctly read the day and month values
    but write them into the YYYY-MM-DD field in the wrong order for the *entire*
    document, not just isolated transactions -- e.g. "2026-13-01" through
    "2026-31-01" (every date in the statement, day value correct, both stuck in
    month's slot) rather than random per-transaction noise. See aidlc-docs/audit.md
    2026-08-02 for the actual failure this was diagnosed from. Detecting via an
    unambiguous month>12 case, then applying the swap to the whole document, avoids
    guessing on individually-ambiguous dates (day<=12, where either order parses as
    "valid" but means something different) in isolation.
    """
    for txn in parsed.get("transactions") or []:
        raw_date = txn.get("transaction_date")
        if not isinstance(raw_date, str):
            continue
        parts = raw_date.split("-")
        if len(parts) != 3:
            continue
        _, month_str, day_str = parts
        if not (month_str.isdigit() and day_str.isdigit()):
            continue
        month, day = int(month_str), int(day_str)
        if month > 12 and 1 <= day <= 12:
            return True
    return False


def _swap_all_transaction_dates(parsed: dict) -> dict:
    def swap_one(txn: dict) -> dict:
        raw_date = txn.get("transaction_date")
        if not isinstance(raw_date, str):
            return txn
        parts = raw_date.split("-")
        if len(parts) != 3:
            return txn
        year, month, day = parts
        return {**txn, "transaction_date": f"{year}-{day}-{month}"}

    return {**parsed, "transactions": [swap_one(txn) for txn in parsed.get("transactions") or []]}


# A "balance brought/carried forward", "previous/opening/closing balance", or
# "(total) outstanding balance" line restates the account's running total -- it is not
# an actual movement of money on that date, and including it as a transaction
# double-counts against whatever real transactions make up that balance (observed
# live: one such line inflated a single month's cash flow by $100,062.66). Two rounds
# of real examples surfaced so far (see aidlc-docs/audit.md 2026-08-02): the first
# pass only covered "brought forward"/"previous balance"; a second live report showed
# "Balance carried forward" (CIMB) and "Total outstanding balance" (Trust Bank) were
# still slipping through -- broadened to the whole family of balance-restatement
# phrasings rather than patching one exact string at a time. The prompt already asks
# Gemini to omit these, but a prompt alone isn't reliable (see the day/month-swap
# experiment earlier this project), so this is the code-level safety net.
_NON_TRANSACTION_DESCRIPTION_PATTERNS = [
    re.compile(r"\bbalance\s+(?:brought|carried)\s+forward\b", re.IGNORECASE),
    re.compile(r"\b(?:previous|opening|closing)\s+balance\b", re.IGNORECASE),
    re.compile(r"\b(?:total\s+)?outstanding\s+balance\b", re.IGNORECASE),
    re.compile(r"\bbal(?:ance)?\.?\s*[bc]\W*f\b", re.IGNORECASE),
]


def _is_non_transaction_line(description: str) -> bool:
    return any(pattern.search(description) for pattern in _NON_TRANSACTION_DESCRIPTION_PATTERNS)


# Administrative/adjustment lines (payments, interest, fees) are not part of a
# statement's day-to-day chronological transaction flow -- e.g. a payment is often
# printed FIRST even though it's dated at the statement's own closing date, and a
# currency-conversion fee is often grouped separately from the transaction it
# belongs to rather than printed in date order. The ambiguous-date correction below
# relies on chronological print order, so these lines are excluded from it and left
# as extracted.
_DATE_CORRECTION_EXCLUDED_DESCRIPTION_PATTERNS = [
    re.compile(r"\bpayment\b", re.IGNORECASE),
    re.compile(r"\binterest\s+charge\b", re.IGNORECASE),
    re.compile(r"\blate\s+(?:charge|fee|payment)\b", re.IGNORECASE),
    re.compile(r"\bcash\s+rebate\b", re.IGNORECASE),
    re.compile(r"\bannual\s+fee\b", re.IGNORECASE),
    re.compile(r"\bccy\s+conversion\s+fee\b", re.IGNORECASE),
]


def _is_excluded_from_date_correction(description: str) -> bool:
    return any(pattern.search(description) for pattern in _DATE_CORRECTION_EXCLUDED_DESCRIPTION_PATTERNS)


def _swap_day_month_if_ambiguous(d: date) -> date | None:
    """Returns the day/month-swapped date, or None if the swap wouldn't be legal
    (day > 12, which would produce an invalid month) or would be a no-op (day ==
    month)."""
    if d.day > 12 or d.day == d.month:
        return None
    return date(d.year, d.day, d.month)


_STATEMENT_DATE_MAX_GAP_DAYS = 45


def _resolve_statement_date(raw_statement_date: date | None, max_trusted_date: date | None) -> date | None:
    """Validates the extracted statement_date against the latest UNAMBIGUOUSLY-parsed
    (day>12, non-excluded) transaction date in the same document, so a Gemini misread
    of statement_date itself (it's just as capable of ambiguous-date confusion as any
    other field) can't poison the excluded-line correction below. A real statement
    date is always on or shortly after its own latest transaction -- if neither the
    extracted value nor its day/month swap falls in that window, it's discarded
    rather than trusted."""
    if raw_statement_date is None or max_trusted_date is None:
        return None
    candidates = [raw_statement_date]
    swapped = _swap_day_month_if_ambiguous(raw_statement_date)
    if swapped is not None:
        candidates.append(swapped)
    window_end = max_trusted_date + timedelta(days=_STATEMENT_DATE_MAX_GAP_DAYS)
    valid = [c for c in candidates if max_trusted_date <= c <= window_end]
    return min(valid) if valid else None


def _correct_ambiguous_transaction_dates(transactions: list, raw_statement_date: date | None = None) -> None:
    """Repairs a real, live-confirmed failure mode distinct from the whole-document
    swap above: for dates where the printed day is individually AMBIGUOUS (<=12,
    where reading it either day-first or month-first produces a calendar-valid
    date), Gemini has been observed to correctly use day-first parsing only when
    forced to (day > 12, where month-first would be invalid) and to inconsistently
    fall back to month-first for the ambiguous ones within the very same document
    -- e.g. a real "3 February" transaction silently committed as "March 3rd",
    while "13 February" elsewhere in the same statement parses correctly. Confirmed
    by manually cross-checking two live OCBC statements' actual PDF pages against
    what got committed to the database -- every regular transaction matched this
    exact signature (see aidlc-docs/audit.md 2026-08-04).

    Statements print transactions in chronological order (the extraction prompt
    already tells Gemini to use this as its own self-check). This repairs ambiguous
    dates in-place by picking whichever of (as-extracted, day/month-swapped) keeps
    the running sequence moving forward with the smallest gap from the previous
    (non-excluded) transaction's already-resolved date -- the same self-check,
    applied here as the code-level backstop the day/month-swap experiment already
    showed a prompt alone isn't reliable for.

    Excluded administrative/fee lines (see _is_excluded_from_date_correction) don't
    follow chronological print order, so the sequential heuristic above isn't safe
    for them -- confirmed live: a "PAYMENT BY INTERNET" line's date, taken at face
    value, would have been wrongly "corrected" to a date almost a month off. But
    they're also not immune to the same ambiguous-date bug (confirmed live on a
    DIFFERENT statement's payment line). Both real examples land exactly on the
    statement's own printed statement_date, so that's used as a second, narrower
    anchor for excluded lines specifically: only applied when one of the two
    candidate dates exactly matches the (cross-validated) statement_date, otherwise
    left as extracted.
    """
    max_trusted_date = max(
        (t.transaction_date for t in transactions if not _is_excluded_from_date_correction(t.description)
         and t.transaction_date.day > 12),
        default=None,
    )
    statement_date = _resolve_statement_date(raw_statement_date, max_trusted_date)

    last_date: date | None = None
    for txn in transactions:
        if _is_excluded_from_date_correction(txn.description):
            if statement_date is not None and txn.transaction_date != statement_date:
                swapped = _swap_day_month_if_ambiguous(txn.transaction_date)
                if swapped is not None and swapped == statement_date:
                    txn.transaction_date = swapped
            continue

        swapped = _swap_day_month_if_ambiguous(txn.transaction_date)
        if swapped is None:
            last_date = txn.transaction_date
            continue

        if last_date is None:
            last_date = txn.transaction_date
            continue

        candidates = [
            ((txn.transaction_date - last_date).days, txn.transaction_date),
            ((swapped - last_date).days, swapped),
        ]
        forward = [c for c in candidates if c[0] >= 0]
        _, chosen_date = min(forward, key=lambda c: c[0]) if forward else min(candidates, key=lambda c: abs(c[0]))
        txn.transaction_date = chosen_date
        last_date = chosen_date


def extract_statement(pdf_bytes: bytes) -> RawExtractedStatement | ExtractionFailure:
    try:
        page_images = _pdf_to_page_images(pdf_bytes)
    except Exception as exc:  # noqa: BLE001 - any PDF-rendering failure is an extraction failure
        return ExtractionFailure(reason=f"Could not render PDF pages: {exc}")

    try:
        raw_response = extract_statement_raw(page_images, EXTRACTION_PROMPT)
    except TransientError as exc:
        # WR-7: no cross-provider fallback -- exhausted retries (clients/retry.py) means terminal failure
        return ExtractionFailure(reason=f"Gemini call failed after retries: {exc}")
    except Exception as exc:  # noqa: BLE001 - any other Gemini error is terminal (WR-1a)
        return ExtractionFailure(reason=f"Gemini call error: {exc}")

    try:
        parsed = _parse_llm_json(raw_response)
        whole_document_swap_applied = _statement_needs_day_month_swap(parsed)
        if whole_document_swap_applied:
            parsed = _swap_all_transaction_dates(parsed)
        statement = RawExtractedStatement.model_validate(parsed)
    except (json.JSONDecodeError, pydantic.ValidationError) as exc:
        # WR-1b: structural/schema validation failure
        return ExtractionFailure(reason=f"Response failed schema validation: {exc}", raw_response=raw_response)

    # Repair individually-ambiguous (day<=12) date misreads -- a DIFFERENT failure
    # mode from the whole-document swap above (that one fires when the WHOLE
    # document uses the wrong convention uniformly, including otherwise-unambiguous
    # dates; this one fires when only the individually-ambiguous dates within an
    # otherwise-correctly-parsed document are wrong). Mutually exclusive with the
    # whole-document swap: once that's already corrected every date uniformly,
    # re-running this per-row heuristic on top would risk "correcting" dates that
    # are already right. See _correct_ambiguous_transaction_dates.
    if not whole_document_swap_applied:
        _correct_ambiguous_transaction_dates(statement.transactions, statement.statement_date)

    # Drop balance-carry-forward lines before any of the checks below, so e.g. the
    # zero-transactions check reflects the real transaction count, not one inflated by
    # a non-transaction summary line.
    statement.transactions = [t for t in statement.transactions if not _is_non_transaction_line(t.description)]

    # Last-resort safety net: a bank statement documents transactions that have
    # already happened, so a transaction_date after today should never reach the
    # database even if the correction above couldn't resolve it (e.g. the excluded
    # administrative/fee lines above, which aren't printed in chronological order).
    today = date.today()
    future_dated = [t for t in statement.transactions if t.transaction_date > today]
    if future_dated:
        logger.warning(
            "Dropping %d transaction(s) with a transaction_date after today (%s): %s",
            len(future_dated), today, [str(t.transaction_date) for t in future_dated],
        )
        statement.transactions = [t for t in statement.transactions if t.transaction_date <= today]

    # WR-2: bank/currency must be identified to commit
    if statement.bank_name is None or statement.currency is None:
        return ExtractionFailure(
            reason="Could not identify bank name and/or currency", raw_response=raw_response
        )

    # WR-1c: zero transactions extracted is treated as a failure (a statement with
    # genuinely no transactions is a rare edge case for this app's use case; simpler
    # and safer to flag for manual review than to silently commit an empty statement)
    if len(statement.transactions) == 0:
        return ExtractionFailure(reason="Zero transactions extracted", raw_response=raw_response)

    # WR-1d: confidence must clear the configured threshold
    threshold = ConfidenceLevel(settings.extraction_confidence_threshold)
    if statement.confidence.rank < threshold.rank:
        return ExtractionFailure(
            reason=f"Extraction confidence '{statement.confidence.value}' below threshold "
            f"'{threshold.value}'",
            raw_response=raw_response,
        )

    return statement
