"""Thin wrapper around google-genai for Ask AI (text-only — unlike ingestion-worker's
statement extraction, no vision/PDF input needed here).

A single attempt, no retry-with-backoff: this is called synchronously within a
user-facing HTTP request (US-6.1's interactive question/answer UX), so a patient
multi-attempt retry chain would just make the browser hang; on failure the user can
simply ask again.
"""

from google import genai
from google.genai import errors as genai_errors

from api_service.config import settings
from api_service.errors import AiServiceUnavailableError


def _client() -> genai.Client:
    return genai.Client(api_key=settings.gemini_api_key)


def ask_gemini(prompt: str, model: str | None = None) -> str:
    """`model` defaults to `settings.gemini_model` (env-configurable: GEMINI_MODEL,
    shared with ingestion-worker's own setting of the same name — see
    aidlc-docs/audit.md), read fresh on each call."""
    model = model or settings.gemini_model
    try:
        client = _client()
        response = client.models.generate_content(model=model, contents=prompt)
        return response.text
    except genai_errors.APIError as exc:
        raise AiServiceUnavailableError(f"AI assistant call failed: {exc}") from exc
    except (TimeoutError, ConnectionError) as exc:
        raise AiServiceUnavailableError(f"AI assistant network error: {exc}") from exc
