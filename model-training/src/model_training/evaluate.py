"""Evaluation logic (FR-CFT-7, MTR-7/8). Split into a pure scoring function
(accuracy/confusion matrix, fully unit-testable given already-known predictions)
and an I/O-performing orchestration function (calls the fine-tuned model + the
live oMLX server for every validation example) -- same pure/impure split
convention this project already uses elsewhere (e.g. ingestion-worker's
currency/service.py)."""

import json
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from model_training import omlx_client


@dataclass
class EvalResult:
    accuracy: float
    confusion_matrix: dict[str, dict[str, int]]
    agreement_with_live_model: float


def score_predictions(
    ground_truth: list[str], fine_tuned_predictions: list[str], live_predictions: list[str]
) -> EvalResult:
    """MTR-8: exact-string-match accuracy; confusion matrix is ground-truth (rows) x
    predicted (columns), an off-whitelist/UNSURE prediction simply never matches a
    real category and is its own column. Pure function -- no I/O, fully
    unit-testable given already-known predictions (test_evaluate.py)."""
    if not (len(ground_truth) == len(fine_tuned_predictions) == len(live_predictions)):
        raise ValueError("ground_truth, fine_tuned_predictions, and live_predictions must be the same length")
    if not ground_truth:
        raise ValueError("cannot score an empty validation set")

    confusion: dict[str, dict[str, int]] = defaultdict(Counter)
    correct = 0
    agree = 0
    for truth, fine_tuned, live in zip(ground_truth, fine_tuned_predictions, live_predictions, strict=True):
        confusion[truth][fine_tuned] += 1
        if fine_tuned == truth:
            correct += 1
        if fine_tuned == live:
            agree += 1

    return EvalResult(
        accuracy=correct / len(ground_truth),
        confusion_matrix={k: dict(v) for k, v in confusion.items()},
        agreement_with_live_model=agree / len(ground_truth),
    )


def evaluate(
    generate_fn: Callable[[str], str], validation_split_path: Path, whitelist: list[str]
) -> EvalResult:
    """Orchestration: reads the validation JSONL (MTR-5 format), gets a prediction
    from the fine-tuned model (via `generate_fn`, supplied by train.py -- keeps this
    module free of a direct mlx_tune import so it stays testable without a real
    model loaded) and from the live oMLX server (MTR-7) for every example, then
    delegates scoring to the pure function above."""
    examples = [json.loads(line) for line in validation_split_path.read_text().splitlines() if line.strip()]

    ground_truth = [ex["messages"][1]["content"] for ex in examples]
    fine_tuned_predictions = [generate_fn(ex["messages"][0]["content"]) for ex in examples]

    # `_description`/`_amount_sgd` are curate.py's own metadata fields (not part of
    # `messages`) -- kept alongside the rendered prompt specifically so evaluate()
    # doesn't have to reverse-parse the prompt text back into its component fields.
    live_predictions = [
        omlx_client.classify_live(ex["_description"], Decimal(ex["_amount_sgd"]), whitelist) for ex in examples
    ]

    return score_predictions(ground_truth, fine_tuned_predictions, live_predictions)
