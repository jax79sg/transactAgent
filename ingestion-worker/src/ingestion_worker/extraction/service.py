"""Statement extraction orchestration (business-logic-model.md — Statement Extraction
Component). Implements WR-1 (extraction failure criteria) and WR-2 (bank/currency
required to commit).
"""

import json
import re
from dataclasses import dataclass

import pydantic
from pdf2image import convert_from_bytes

from ingestion_worker.clients.gemini_client import extract_statement_raw
from ingestion_worker.clients.retry import TransientError
from ingestion_worker.config import settings
from ingestion_worker.extraction.prompts import EXTRACTION_PROMPT
from ingestion_worker.extraction.schemas import ConfidenceLevel, RawExtractedStatement


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
        if _statement_needs_day_month_swap(parsed):
            parsed = _swap_all_transaction_dates(parsed)
        statement = RawExtractedStatement.model_validate(parsed)
    except (json.JSONDecodeError, pydantic.ValidationError) as exc:
        # WR-1b: structural/schema validation failure
        return ExtractionFailure(reason=f"Response failed schema validation: {exc}", raw_response=raw_response)

    # Drop balance-carry-forward lines before any of the checks below, so e.g. the
    # zero-transactions check reflects the real transaction count, not one inflated by
    # a non-transaction summary line.
    statement.transactions = [t for t in statement.transactions if not _is_non_transaction_line(t.description)]

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
