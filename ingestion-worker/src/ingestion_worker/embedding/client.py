"""EmbeddingClient (business-logic-model.md — Embedding Manager Component,
nfr-design-patterns.md's "No-Retry Immediate Soft-Fail" pattern).

Deliberately does NOT use clients/retry.py's retry-with-backoff decorator — WR-25
requires a single attempt, immediate soft-fail on any error class, since the
embedding path is a soft dependency (FR-10) with an already-fast, correct fallback
(the existing fuzzy-text matcher). Uses the `openai` SDK against an
OpenAI-compatible embeddings endpoint, same library/assumption as
clients/openrouter_client.py's chat-completions call, since oMLX is expected to
expose an OpenAI-compatible API surface.
"""

import logging

from openai import OpenAI

from ingestion_worker.config import settings

logger = logging.getLogger(__name__)

# Short and bounded, unlike openrouter_client.py's 60s -- there is no retry here to
# amortize a slow attempt over, and a hung call must not stall the whole poll cycle
# (same "explicit bounded timeout" lesson as openrouter_client.py's own comment,
# applied preemptively rather than after an incident).
_REQUEST_TIMEOUT_SECONDS = 5.0


def _client() -> OpenAI:
    return OpenAI(
        # Falls back to openrouter_api_key, then "not-required" (SDK requires a
        # non-empty string) -- covers servers with no auth, servers that share
        # OPENROUTER_API_KEY, and servers with their own EMBEDDING_API_KEY.
        api_key=settings.embedding_api_key or settings.openrouter_api_key or "not-required",
        base_url=settings.embedding_base_url,
        timeout=_REQUEST_TIMEOUT_SECONDS,
    )


def compute_embedding(text: str) -> list[float] | None:
    """WR-24: `text` is passed through exactly as given, raw and unnormalized --
    WR-20's `normalize_reference_noise` is never applied to embedding input.

    Returns `None` (the EmbeddingUnavailable sentinel, domain-entities.md) on ANY
    failure -- unset config, unreachable endpoint, timeout, non-2xx response, or an
    unexpected response shape. Every caller treats `None` identically: fall through
    to the existing fuzzy-text path (WR-21 step 4).
    """
    if not settings.embedding_base_url:
        return None  # NFR-5: unset is normal, not an error
    try:
        response = _client().embeddings.create(model=settings.embedding_model, input=text)
        vector = response.data[0].embedding
    except Exception:
        # with no retry (contrast clients/retry.py's TransientError-only retry scope).
        logger.info("Embedding computation unavailable (endpoint unreachable or errored)", exc_info=True)
        return None
    if not vector:
        logger.warning("Embedding endpoint returned an empty vector, treating as unavailable")
        return None
    return [float(x) for x in vector]
