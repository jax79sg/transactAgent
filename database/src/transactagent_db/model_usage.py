"""Recording what a paid cloud model call cost (issue #28, Model Cost Page).

Shared by both backend services so the arithmetic, the token estimate and the soft-fail rule exist exactly once.
Each service passes its own session factory and its own copy of the three prices from Settings.
"""

import logging
import math
from collections.abc import Callable
from decimal import Decimal

from sqlalchemy.orm import Session

from transactagent_db.models import ModelUsage

logger = logging.getLogger(__name__)

PROVIDER_GEMINI = "gemini"

PURPOSE_STATEMENT_EXTRACTION = "statement_extraction"
PURPOSE_CATEGORIZATION = "categorization"
PURPOSE_EMBEDDING = "embedding"
PURPOSE_ASK_AI = "ask_ai"
PURPOSES = (PURPOSE_STATEMENT_EXTRACTION, PURPOSE_CATEGORIZATION, PURPOSE_EMBEDDING, PURPOSE_ASK_AI)

_MILLION = Decimal(1_000_000)
# Rule of thumb for English text and the only estimate available when the provider reports nothing (MC-3).
_CHARS_PER_TOKEN_ESTIMATE = 4


def estimate_tokens(text: str) -> int:
    """One token per four characters, rounded up, never less than one."""
    return max(1, math.ceil(len(text) / _CHARS_PER_TOKEN_ESTIMATE))


def _count(value) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def tokens_from_genai_usage(usage) -> tuple[int, int] | None:
    """(input, output) tokens from a google-genai response's `usage_metadata`, or None if the response carried none.
    Thinking tokens are billed as output, so they count as output; where the reported total is larger than the parts
    (tool-use tokens, say) the difference is output too, so the cost is never understated."""
    if usage is None:
        return None
    tokens_in = _count(getattr(usage, "prompt_token_count", None))
    tokens_out = _count(getattr(usage, "candidates_token_count", None)) + _count(
        getattr(usage, "thoughts_token_count", None)
    )
    total = _count(getattr(usage, "total_token_count", None))
    return tokens_in, max(tokens_out, total - tokens_in)


def tokens_from_openai_usage(usage) -> tuple[int, int] | None:
    """(input, output) tokens from an OpenAI-style `usage` object (Gemini's OpenAI-compatible endpoint), or None if
    the response carried none. Output is the larger of the completion count and total minus prompt, same reason."""
    if usage is None:
        return None
    tokens_in = _count(getattr(usage, "prompt_tokens", None))
    completion = _count(getattr(usage, "completion_tokens", None))
    total = _count(getattr(usage, "total_tokens", None))
    return tokens_in, max(completion, total - tokens_in)


def compute_cost_usd(
    input_tokens: int, output_tokens: int, input_price_per_million: float, output_price_per_million: float
) -> Decimal:
    """Exact decimal arithmetic (prices arrive as floats from Settings, so go through str to avoid float noise)."""
    return (
        Decimal(input_tokens) * Decimal(str(input_price_per_million))
        + Decimal(output_tokens) * Decimal(str(output_price_per_million))
    ) / _MILLION


def record_model_usage(
    session_factory: Callable[[], Session],
    *,
    purpose: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    input_price_per_million: float,
    output_price_per_million: float,
    tokens_estimated: bool = False,
    provider: str = PROVIDER_GEMINI,
) -> None:
    """Writes one usage row in its OWN short transaction and swallows every failure (MC-4): recording is
    bookkeeping about a call that already happened, so it must never fail or delay the call it describes, and
    because it commits independently a later rollback of the caller's own work cannot erase money already spent."""
    try:
        if purpose not in PURPOSES:
            raise ValueError(f"unknown model usage purpose {purpose!r}")
        row = ModelUsage(
            purpose=purpose,
            provider=provider,
            model=model,
            input_tokens=max(0, int(input_tokens)),
            output_tokens=max(0, int(output_tokens)),
            tokens_estimated=tokens_estimated,
            cost_usd=compute_cost_usd(
                max(0, int(input_tokens)), max(0, int(output_tokens)), input_price_per_million, output_price_per_million
            ),
        )
        session = session_factory()
        try:
            session.add(row)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except Exception:
        logger.warning("Could not record %s model usage (the call itself is unaffected)", purpose, exc_info=True)
