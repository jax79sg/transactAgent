"""MTR-7: a thin, independent OpenAI-compatible client for evaluate()'s live-model
comparison calls -- reaches the SAME oMLX server ingestion-worker's
openrouter_client.py talks to, but directly, not through ingestion-worker's code
(Model Training has zero import dependency on that package, per Application
Design). No retry/backoff (unlike ingestion-worker's WR-7 retry_with_backoff) --
NFR Design's "fail loud" pattern: an evaluate() run that can't reach the live
model should stop and say so, not silently degrade.
"""

from decimal import Decimal

from openai import OpenAI

from model_training.config import settings
from model_training.prompt import render_classification_prompt


def classify_live(description: str, amount_sgd: Decimal | None, whitelist: list[str]) -> str:
    """Returns the live oMLX-served model's raw text answer, using the byte-identical
    prompt template MTR-5/render_classification_prompt defines -- not normalized or
    validated against the whitelist here (evaluate() does that itself, same as
    accuracy scoring treats an off-whitelist answer as simply incorrect, MTR-8)."""
    client = OpenAI(api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url)
    response = client.chat.completions.create(
        model=settings.openrouter_model,
        messages=[{"role": "user", "content": render_classification_prompt(description, amount_sgd, whitelist)}],
        temperature=0,
    )
    return (response.choices[0].message.content or "").strip()
