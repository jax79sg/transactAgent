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
from dataclasses import dataclass

from openai import OpenAI

from ingestion_worker.clients.openrouter_client import GEMINI_OPENAI_BASE_URL
from ingestion_worker.config import settings
from ingestion_worker.usage import record_embedding_call

logger = logging.getLogger(__name__)

# Short and bounded, unlike openrouter_client.py's 60s -- there is no retry here to
# amortize a slow attempt over, and a hung call must not stall the whole poll cycle
# (same "explicit bounded timeout" lesson as openrouter_client.py's own comment,
# applied preemptively rather than after an incident).
_REQUEST_TIMEOUT_SECONDS = 5.0
# A cloud endpoint is slower and burstier than a local server; still bounded, still no retry.
_GEMINI_REQUEST_TIMEOUT_SECONDS = 15.0

# Gemini Embedding 2 takes its task as text in the prompt (there is no task_type parameter for text). "classification"
# was chosen on the user's own labelled transactions (2026-10-05): at the same precision it matched far more
# neighbours than the raw text (e.g. ~99% precision at 68% coverage vs 23%). It is applied to BOTH the stored and
# the query side, because both go through compute_embedding.
GEMINI_TASK_PREFIX = "task: classification | query: "


@dataclass(frozen=True)
class _Provider:
    name: str
    base_url: str
    api_key: str
    model: str
    timeout: float
    dimensions: int | None  # asked of the server and checked on the reply; None = take whatever the server returns
    prefix: str


def _provider() -> _Provider:
    """Read fresh on every call. `gemini` reuses the extraction key; `local` is the configurable OpenAI-compatible
    server, exactly as before (an empty base URL still means embeddings are off, NFR-5)."""
    if settings.embedding_provider == "gemini":
        return _Provider(
            "gemini", GEMINI_OPENAI_BASE_URL, settings.gemini_api_key, settings.gemini_embedding_model,
            _GEMINI_REQUEST_TIMEOUT_SECONDS, settings.embedding_dimensions, GEMINI_TASK_PREFIX,
        )
    return _Provider(
        "local", settings.embedding_base_url,
        # Falls back to openrouter_api_key, then "not-required" (SDK requires a non-empty string) -- covers servers
        # with no auth, servers that share OPENROUTER_API_KEY, and servers with their own EMBEDDING_API_KEY.
        settings.embedding_api_key or settings.openrouter_api_key or "not-required",
        settings.embedding_model, _REQUEST_TIMEOUT_SECONDS, None, "",
    )


def _client() -> OpenAI:
    provider = _provider()
    return OpenAI(api_key=provider.api_key, base_url=provider.base_url, timeout=provider.timeout)


def compute_embedding(text: str) -> list[float] | None:
    """WR-24: `text` is passed through exactly as given, raw and unnormalized --
    WR-20's `normalize_reference_noise` is never applied to embedding input.

    Returns `None` (the EmbeddingUnavailable sentinel, domain-entities.md) on ANY
    failure -- unset config, unreachable endpoint, timeout, non-2xx response, or an
    unexpected response shape. Every caller treats `None` identically: fall through
    to the existing fuzzy-text path (WR-21 step 4).
    """
    provider = _provider()
    if not provider.base_url:
        return None  # NFR-5: unset is normal, not an error
    request = {"model": provider.model, "input": provider.prefix + text}
    if provider.dimensions is not None:
        request["dimensions"] = provider.dimensions
    try:
        response = _client().embeddings.create(**request)
        vector = response.data[0].embedding
        if provider.name == "gemini":
            # Issue #28 (Costs page): the call succeeded and is billed, whatever is then thought of the vector. Gemini
            # reports no usage here, so the tokens are estimated from the text actually sent. Never raises.
            record_embedding_call(provider.model, request["input"])
    except Exception:
        # with no retry (contrast clients/retry.py's TransientError-only retry scope).
        logger.info("Embedding computation unavailable (endpoint unreachable or errored)", exc_info=True)
        return None
    if not vector:
        logger.warning("Embedding endpoint returned an empty vector, treating as unavailable")
        return None
    if provider.dimensions is not None and len(vector) != provider.dimensions:
        # A wrong-sized vector would be rejected by the vector store (and would hide behind a generic failure there).
        logger.warning(
            "Embedding endpoint returned %d dimensions but embedding_dimensions is %d, treating as unavailable",
            len(vector), provider.dimensions,
        )
        return None
    return [float(x) for x in vector]
