"""Thin wrapper around google-genai for statement extraction (vision/PDF input).

Functional Design Question 2 = A: PDF pages are sent directly to Gemini as images,
asking it to both read the page and extract structured transaction data in one call.
"""

from google import genai
from google.genai import errors as genai_errors

from ingestion_worker.clients.retry import TransientError, retry_with_backoff
from ingestion_worker.config import settings

_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}

# Explicit, bounded timeout rather than relying on the SDK's own default -- see
# clients/openrouter_client.py's _REQUEST_TIMEOUT_SECONDS for the real incident
# (2026-08-04) this class of risk caused elsewhere in the same pipeline. Extraction
# involves larger payloads (page images) than categorization, so a longer ceiling.
_REQUEST_TIMEOUT_MS = 120_000


def _client() -> genai.Client:
    return genai.Client(
        api_key=settings.gemini_api_key,
        http_options=genai.types.HttpOptions(timeout=_REQUEST_TIMEOUT_MS),
    )


@retry_with_backoff()
def extract_statement_raw(page_images: list[bytes], prompt: str, model: str | None = None) -> str:
    """Sends the PDF page images + extraction prompt to Gemini, returns the raw text
    response (expected to be JSON — validated by extraction/service.py).

    `model` defaults to `settings.gemini_model` (env-configurable: GEMINI_MODEL, per
    user request 2026-08-01), read fresh on each call rather than bound as a function
    default at import time -- the default is "gemini-3.5-flash-lite" (accepts
    Text/Image/Video/Audio/PDF input, supports structured outputs -- see
    https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite). Originally
    defaulted to gemini-3.1-flash-lite; switched 2026-08-02 after that model was found
    to consistently transpose day/month for at least one bank's day-first-printed
    dates -- verified via 3 live extraction runs against the real failing statement
    that gemini-3.5-flash-lite does not exhibit this (see aidlc-docs/audit.md). Any
    model you configure must support image input, since this call always sends page
    images.
    """
    model = model or settings.gemini_model
    try:
        client = _client()
        parts = [genai.types.Part.from_bytes(data=img, mime_type="image/png") for img in page_images]
        parts.append(prompt)
        response = client.models.generate_content(model=model, contents=parts)
        return response.text
    except genai_errors.APIError as exc:
        status_code = getattr(exc, "code", None)
        if status_code in _TRANSIENT_STATUS_CODES:
            raise TransientError(f"Gemini transient error (status {status_code}): {exc}") from exc
        raise
    except (TimeoutError, ConnectionError) as exc:
        raise TransientError(f"Gemini network error: {exc}") from exc
