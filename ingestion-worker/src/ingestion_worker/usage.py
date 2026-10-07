"""The worker's side of the Costs page (issue #28): prices a Gemini call from Settings and records it.

A thin layer over transactagent_db.model_usage, which holds the arithmetic and the never-fail rule. Called right
after a response arrives and before anything is parsed, so spend is recorded even when the caller then rejects the
answer.
"""

from transactagent_db.model_usage import (
    PURPOSE_EMBEDDING,
    estimate_tokens,
    record_model_usage,
    tokens_from_genai_usage,
    tokens_from_openai_usage,
)

from ingestion_worker.config import settings
from ingestion_worker.db import SessionLocal


def record_genai_call(purpose: str, model: str, response) -> None:
    """A google-genai response (statement extraction)."""
    _record(purpose, model, tokens_from_genai_usage(getattr(response, "usage_metadata", None)))


def record_openai_call(purpose: str, model: str, response) -> None:
    """A response from Gemini's OpenAI-compatible chat endpoint (categorisation)."""
    _record(purpose, model, tokens_from_openai_usage(getattr(response, "usage", None)))


def record_embedding_call(model: str, text: str) -> None:
    """Gemini's embeddings endpoint reports no usage, so the input tokens are an estimate and the row says so (MC-3)."""
    record_model_usage(
        SessionLocal, purpose=PURPOSE_EMBEDDING, model=model, input_tokens=estimate_tokens(text), output_tokens=0,
        input_price_per_million=settings.gemini_embedding_price_per_million_usd, output_price_per_million=0.0,
        tokens_estimated=True,
    )


def _record(purpose: str, model: str, tokens: tuple[int, int] | None) -> None:
    if tokens is None:  # the response carried no usage, so there is nothing true to record
        return
    record_model_usage(
        SessionLocal, purpose=purpose, model=model, input_tokens=tokens[0], output_tokens=tokens[1],
        input_price_per_million=settings.gemini_input_price_per_million_usd,
        output_price_per_million=settings.gemini_output_price_per_million_usd,
    )
