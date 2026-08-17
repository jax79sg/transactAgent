"""MTR-5: renders the exact SAME prompt text ingestion-worker's
openrouter_client.py's classify_description() builds (WR-34) -- Model Training has
zero import dependency on ingestion-worker's package (Application Design), so this
is an independent, deliberately-duplicated copy, not a shared import. Kept
byte-identical by a cross-check test at Build and Test, not by a shared function --
see build-and-test-summary.md for that verification.
"""

from decimal import Decimal

_UNKNOWN_AMOUNT = "unknown"


def format_amount_sgd(amount_sgd: Decimal | None) -> str:
    return f"{amount_sgd} SGD" if amount_sgd is not None else _UNKNOWN_AMOUNT


def render_classification_prompt(description: str, amount_sgd: Decimal | None, whitelist: list[str]) -> str:
    """Byte-identical to ingestion_worker.clients.openrouter_client.classify_description's
    prompt (WR-34) -- this is the whole point of MTR-5/Requirements' Resolved
    Decision 5/6: training input must match live input exactly."""
    return (
        "Classify this bank transaction description into exactly one of the following "
        "categories, responding with ONLY the category name and nothing else:\n\n"
        f"Categories: {', '.join(whitelist)}\n\n"
        f"Transaction description: {description}\n"
        f"Transaction amount: {format_amount_sgd(amount_sgd)}\n\n"
        "If none of the categories clearly fit, respond with exactly: UNSURE"
    )
