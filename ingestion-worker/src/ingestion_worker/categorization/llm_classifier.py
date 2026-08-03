"""LLM categorization fallback (WR-4: constrained to whitelist, UNSURE on any failure)."""

from ingestion_worker.clients.openrouter_client import classify_description
from ingestion_worker.clients.retry import TransientError

UNSURE = "UNSURE"


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
