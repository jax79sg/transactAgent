"""Thin wrapper around an OpenAI-compatible chat completions API for categorization
fallback. Defaults to OpenRouter but works against any OpenAI-compatible endpoint
(base_url is env-configurable via OPENROUTER_BASE_URL, e.g. a local model server).

Text-only, constrained to the whitelist + "UNSURE" (WR-4).
"""

from openai import APIStatusError, OpenAI

from ingestion_worker.clients.retry import TransientError, retry_with_backoff
from ingestion_worker.config import settings

_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url)


@retry_with_backoff()
def classify_description(description: str, whitelist: list[str], model: str | None = None) -> str:
    """Returns the model's raw text answer (validated against the whitelist by
    categorization/llm_classifier.py — this wrapper does not itself enforce WR-4).

    `model` defaults to `settings.openrouter_model` (env-configurable: OPENROUTER_MODEL,
    per user request 2026-08-01), read fresh on each call rather than bound as a
    function default at import time. The default confirmed to work here,
    "openrouter/free", is OpenRouter's own free-models router -- it auto-selects among
    free-tier models with capability-matched filtering, rather than pinning to one
    specific model that could be deprecated/rate-limited. See
    https://openrouter.ai/openrouter/free.
    """
    model = model or settings.openrouter_model
    prompt = (
        "Classify this bank transaction description into exactly one of the following "
        "categories, responding with ONLY the category name and nothing else:\n\n"
        f"Categories: {', '.join(whitelist)}\n\n"
        f"Transaction description: {description}\n\n"
        "If none of the categories clearly fit, respond with exactly: UNSURE"
    )
    try:
        client = _client()
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        return (response.choices[0].message.content or "").strip()
    except APIStatusError as exc:
        if exc.status_code in _TRANSIENT_STATUS_CODES:
            raise TransientError(
                f"Categorization LLM transient error ({settings.openrouter_base_url}, "
                f"status {exc.status_code}): {exc}"
            ) from exc
        raise
    except (TimeoutError, ConnectionError) as exc:
        raise TransientError(
            f"Categorization LLM network error ({settings.openrouter_base_url}): {exc}"
        ) from exc
