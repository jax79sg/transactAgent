"""The API's side of the Costs page (issue #28): prices an Ask AI call from Settings and records it.

A thin layer over transactagent_db.model_usage, which holds the arithmetic and the never-fail rule (see also the
worker's own ingestion_worker/usage.py). Called right after the response arrives, before the answer is used.
"""

from transactagent_db.model_usage import (
    PURPOSE_ASK_AI,
    record_model_usage,
    tokens_from_genai_usage,
)

from api_service.config import settings
from api_service.db import SessionLocal


def record_ask_ai_call(model: str, response) -> None:
    tokens = tokens_from_genai_usage(getattr(response, "usage_metadata", None))
    if tokens is None:  # the response carried no usage, so there is nothing true to record
        return
    record_model_usage(
        SessionLocal, purpose=PURPOSE_ASK_AI, model=model, input_tokens=tokens[0], output_tokens=tokens[1],
        input_price_per_million=settings.gemini_input_price_per_million_usd,
        output_price_per_million=settings.gemini_output_price_per_million_usd,
    )
