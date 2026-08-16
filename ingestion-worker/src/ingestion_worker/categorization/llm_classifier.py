"""LLM categorization fallback (WR-4: constrained to whitelist, UNSURE on any failure)."""

import json
import re

from ingestion_worker.clients.openrouter_client import classify_description, classify_descriptions_batch
from ingestion_worker.clients.retry import TransientError

UNSURE = "UNSURE"

_JSON_ARRAY = re.compile(r"\[.*\]", re.DOTALL)


def classify(description: str, whitelist: list[str]) -> str:
    """Always returns a value in `whitelist` or the literal UNSURE — never raises,
    never returns a free-text/invalid value (WR-4)."""
    try:
        answer = classify_description(description, whitelist)
    except TransientError:
        # WR-7: exhausted retries, no cross-provider fallback -- terminal for this transaction
        return UNSURE
    except Exception:  # noqa: BLE001 - any other OpenRouter error is also terminal
        return UNSURE

    normalized = answer.strip()
    if normalized in whitelist:
        return normalized
    return UNSURE


def classify_batch_prompt(descriptions: list[str], whitelist: list[str]) -> dict[str, str]:
    """Matching Precision Refinement (WR-27, revised): classifies a whole batch in
    one call, returning only the entries it could confidently parse and validate --
    a description missing from the returned dict (network/parse failure, a
    too-short response, or an entry that wasn't a whitelist name / "UNSURE") is
    simply absent, never a raised exception (same WR-4 "never raises" contract as
    `classify()`). The caller (`categorization/service.py`'s `classify_batch`) is
    responsible for falling every missing description back to an individual
    `classify()` call -- this function only ever returns a subset, never guesses.

    `descriptions` must already be de-duplicated by the caller (a repeated
    description would collide as a dict key here).
    """
    try:
        raw = classify_descriptions_batch(descriptions, whitelist)
    except TransientError:
        return {}
    except Exception:  # noqa: BLE001 - any other OpenRouter error -- whole batch falls back
        return {}

    match = _JSON_ARRAY.search(raw)
    if match is None:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, list):
        return {}

    result: dict[str, str] = {}
    for description, answer in zip(descriptions, parsed):
        if not isinstance(answer, str):
            continue
        normalized = answer.strip()
        if normalized in whitelist or normalized == UNSURE:
            result[description] = normalized
    return result
