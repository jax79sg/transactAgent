"""LLM categorization fallback (WR-4: constrained to whitelist, UNSURE on any failure)."""

import json
import re
from decimal import Decimal

from ingestion_worker.clients.openrouter_client import (
    classify_description,
    classify_descriptions_batch,
)
from ingestion_worker.clients.retry import TransientError

UNSURE = "UNSURE"

_JSON_ARRAY = re.compile(r"\[.*\]", re.DOTALL)


def classify(description: str, amount_sgd: Decimal | None, whitelist: list[str]) -> str:
    """Always returns a value in `whitelist` or the literal UNSURE — never raises,
    never returns a free-text/invalid value (WR-4).

    `amount_sgd` (WR-34): the transaction's converted SGD amount, included in the
    prompt alongside `description`; `None` when conversion was unavailable."""
    try:
        answer = classify_description(description, amount_sgd, whitelist)
    except TransientError:
        # WR-7: exhausted retries, no cross-provider fallback -- terminal for this transaction
        return UNSURE
    except Exception:  # noqa: BLE001 - any other OpenRouter error is also terminal
        return UNSURE

    normalized = answer.strip()
    if normalized in whitelist:
        return normalized
    return UNSURE


def classify_batch_prompt(items: list[tuple[str, Decimal | None]], whitelist: list[str]) -> dict[str, str]:
    """Matching Precision Refinement (WR-27, revised): classifies a whole batch in
    one call, returning only the entries it could confidently parse and validate --
    a description missing from the returned dict (network/parse failure, a
    too-short response, or an entry that wasn't a whitelist name / "UNSURE") is
    simply absent, never a raised exception (same WR-4 "never raises" contract as
    `classify()`). The caller (`categorization/service.py`'s `classify_batch`) is
    responsible for falling every missing description back to an individual
    `classify()` call -- this function only ever returns a subset, never guesses.

    `items` is a list of (description, amountSgd) pairs (WR-34) and must already
    be de-duplicated by description by the caller (a repeated description would
    collide as a dict key here).
    """
    try:
        raw = classify_descriptions_batch(items, whitelist)
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
    # strict=False deliberately: a shorter-than-requested `parsed` array is an
    # expected, tested outcome (a too-short LLM response), not a bug -- the
    # trailing items are simply left unanswered here, per this function's own
    # docstring ("a description missing from the returned dict... is simply
    # absent, never a raised exception").
    for (description, _amount_sgd), answer in zip(items, parsed, strict=False):
        if not isinstance(answer, str):
            continue
        normalized = answer.strip()
        if normalized in whitelist or normalized == UNSURE:
            result[description] = normalized
    return result
