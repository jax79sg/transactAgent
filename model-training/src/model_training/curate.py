"""Dataset Curator Component (FR-CFT-1..4). CLI entry point: `python -m
model_training.curate [--output-dir DIR] [--train-split-ratio 0.85]`.

NFR Design: fails loudly (a DB connection error, an empty result set) rather than
degrading silently -- this is a manually-run, single-operator tool, not an
unattended background process.
"""

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from model_training import repository
from model_training.config import settings
from model_training.prompt import render_classification_prompt

UNSURE_NAME = "UNSURE"


@dataclass
class CurationSummary:
    train_count: int
    val_count: int
    source_breakdown: dict[str, int]
    excluded_null_amount_count: int


def curate_dataset(db: Session, output_dir: Path, train_split_ratio: float = 0.85) -> CurationSummary:
    eligible = repository.find_eligible_transactions(db)  # MTR-1

    usable = [row for row in eligible if row.amount_sgd is not None]  # MTR-2
    excluded_null_count = len(eligible) - len(usable)

    source_breakdown: dict[str, int] = {}
    for row in usable:
        source_breakdown[row.category_source.value] = source_breakdown.get(row.category_source.value, 0) + 1

    # MTR-4: already sorted by transaction_id (repository query's own ORDER BY) --
    # deterministic given the same DB state, no re-sort needed here.
    split_index = int(len(usable) * train_split_ratio)
    train_rows, val_rows = usable[:split_index], usable[split_index:]

    whitelist = [name for name in repository.list_active_category_names(db) if name != UNSURE_NAME]

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output_dir / "train.jsonl", train_rows, whitelist)
    _write_jsonl(output_dir / "val.jsonl", val_rows, whitelist)

    return CurationSummary(
        train_count=len(train_rows),
        val_count=len(val_rows),
        source_breakdown=source_breakdown,
        excluded_null_amount_count=excluded_null_count,
    )


def _write_jsonl(path: Path, rows, whitelist: list[str]) -> None:
    """MTR-5: one SFT-style chat example per line. Fields prefixed `_` are metadata
    for this project's own tooling (traceability, and evaluate()'s live-model
    comparison, MTR-7) -- never fed to the model as training input; only `messages`
    is."""
    with path.open("w") as f:
        for row in rows:
            user_content = render_classification_prompt(row.description, row.amount_sgd, whitelist)
            example = {
                "messages": [
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": row.category_name},
                ],
                "_transaction_id": str(row.transaction_id),
                "_description": row.description,
                "_amount_sgd": str(row.amount_sgd),  # Decimal isn't JSON-serializable directly
            }
            f.write(json.dumps(example) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Curate a fine-tuning dataset from labeled transactions.")
    parser.add_argument("--output-dir", type=Path, default=Path("dataset"))
    parser.add_argument("--train-split-ratio", type=float, default=0.85)
    args = parser.parse_args()

    engine = create_engine(settings.database_url)
    with Session(engine) as db:
        summary = curate_dataset(db, args.output_dir, args.train_split_ratio)

    print(json.dumps(asdict(summary), indent=2))
    if summary.train_count == 0:
        raise SystemExit("No eligible transactions found -- nothing to train on. See source_breakdown above.")


if __name__ == "__main__":
    main()
