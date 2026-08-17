"""Fine-Tuning Trainer Component (FR-CFT-5..8). CLI entry point: `python -m
model_training.train --dataset-dir DIR --steps N [--output-dir DIR]
[--save-format lora_adapter|merged]`.

Imports mlx_tune only here (not in evaluate.py/curate.py) so those modules stay
importable/testable on a machine without a real MLX runtime -- NFR Requirements'
"Two-Speed Testability" pattern.

**Gemma 4 is a VLM, even for text-only tasks** (confirmed against mlx-tune's own
`examples/39_gemma4_text_to_sql.py` and `examples/40_gemma4_moe_finetuning.py`,
both real, runnable examples targeting this exact model family): the plain
`FastLanguageModel`/`SFTTrainer` path shown in mlx-tune's top-level README quick
start does not apply to `gemma-4-26b-a4b-it-4bit` -- `FastVisionModel`/
`VLMSFTTrainer`/`VLMSFTConfig` are required instead, and every chat-message
`content` field must be a list of `{"type": "text", "text": ...}` parts (the VLM
multi-modal shape), not a plain string, even with no image involved.
"""

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from clearml import Task

from model_training import evaluate as evaluate_module
from model_training.config import settings

# MTR-9: fixed project name (not configurable) so every run lands in one place.
_CLEARML_PROJECT = "transactagent-categorization-finetuning"
_BASE_MODEL = "mlx-community/gemma-4-26b-a4b-it-4bit"


@dataclass
class TrainingConfig:
    lora_rank: int = 16  # MTR-6 defaults, matching mlx-tune's own Gemma-4 examples
    lora_alpha: int = 16
    learning_rate: float = 2e-4
    steps: int = 100
    max_length: int = 512
    save_format: str = "lora_adapter"


@dataclass
class TrainingRunResult:
    clearml_task_id: str
    artifact_path: str
    accuracy: float
    agreement_with_live_model: float


def _to_vlm_messages(jsonl_line: dict) -> dict:
    """Adapts curate.py's plain-string `messages` (tool-agnostic, per MTR-5) into
    the VLM multi-modal content-list shape mlx-tune's `VLMSFTTrainer`/
    `UnslothVisionDataCollator` require for Gemma 4 -- kept as a conversion step
    here, not baked into curate.py's own output, so Dataset Curator stays free of
    any mlx-tune-specific/model-specific assumption (NFR Requirements:
    Dataset Curator has zero ML-runtime dependency)."""
    return {
        "messages": [
            {"role": m["role"], "content": [{"type": "text", "text": m["content"]}]}
            for m in jsonl_line["messages"]
        ]
    }


def _load_vlm_dataset(path: Path) -> list[dict]:
    lines = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [_to_vlm_messages(line) for line in lines]


def train(dataset_dir: Path, output_dir: Path, config: TrainingConfig) -> TrainingRunResult:
    from mlx_tune import FastVisionModel, UnslothVisionDataCollator, VLMSFTTrainer  # noqa: PLC0415
    from mlx_tune.vlm import VLMSFTConfig  # noqa: PLC0415

    task = Task.init(project_name=_CLEARML_PROJECT, task_name=f"finetune-{datetime.now(timezone.utc).isoformat()}")
    task.connect(asdict(config))

    model, processor = FastVisionModel.from_pretrained(_BASE_MODEL, load_in_4bit=True)
    model = FastVisionModel.get_peft_model(
        model,
        finetune_vision_layers=False,  # text-only task -- no image input ever
        finetune_language_layers=True,
        finetune_attention_modules=True,
        finetune_mlp_modules=True,
        r=config.lora_rank,
        lora_alpha=config.lora_alpha,
        lora_dropout=0,
        bias="none",
        random_state=3407,  # matches mlx-tune's own Gemma-4 examples' seed
    )

    train_dataset = _load_vlm_dataset(dataset_dir / "train.jsonl")

    trainer = VLMSFTTrainer(
        model=model,
        tokenizer=processor,
        data_collator=UnslothVisionDataCollator(model, processor),
        train_dataset=train_dataset,
        args=VLMSFTConfig(
            per_device_train_batch_size=1,
            gradient_accumulation_steps=4,
            warmup_steps=5,
            max_steps=config.steps,
            learning_rate=config.learning_rate,
            logging_steps=1,
            optim="adam",
            weight_decay=0.001,
            lr_scheduler_type="linear",
            seed=3407,
            output_dir=str(output_dir),
            report_to="none",
            remove_unused_columns=False,
            dataset_text_field="",
            dataset_kwargs={"skip_prepare_dataset": True},
            max_length=config.max_length,
        ),
    )
    trainer.train()

    FastVisionModel.for_inference(model)

    def generate_fn(prompt: str) -> str:
        return model.generate(prompt=prompt, max_tokens=32, temperature=0).strip()

    whitelist = _whitelist_from_dataset(dataset_dir)
    eval_result = evaluate_module.evaluate(generate_fn, dataset_dir / "val.jsonl", whitelist)

    logger = task.get_logger()
    logger.report_table(title="confusion_matrix", series="val", table_plot=eval_result.confusion_matrix)  # MTR-8
    logger.report_scalar(title="accuracy", series="val", value=eval_result.accuracy, iteration=config.steps)
    logger.report_scalar(
        title="agreement_with_live_model", series="val", value=eval_result.agreement_with_live_model,
        iteration=config.steps,
    )

    artifact_path = save_artifact(model, output_dir, config.save_format)
    task.upload_artifact(name="model", artifact_object=str(artifact_path))
    task.close()

    return TrainingRunResult(
        clearml_task_id=task.id,
        artifact_path=str(artifact_path),
        accuracy=eval_result.accuracy,
        agreement_with_live_model=eval_result.agreement_with_live_model,
    )


def save_artifact(model, output_dir: Path, save_format: str) -> Path:
    """FR-CFT-8: local save only -- no conversion, no deployment call
    (Resolved Decision 7). `merged` isn't offered by mlx-tune's VLM path in the
    same form as its plain-text FastLanguageModel path (no
    save_pretrained_merged on FastVisionModel in the examples reviewed) --
    `save_format` is retained as a CLI option for forward-compatibility, but only
    `lora_adapter` is implemented; requesting `merged` fails loudly rather than
    silently falling back."""
    if save_format != "lora_adapter":
        raise NotImplementedError(
            f"save_format={save_format!r} is not supported for Gemma 4 (VLM path) -- only 'lora_adapter' is."
        )
    artifact_path = output_dir / "artifact"
    model.save_pretrained(str(artifact_path))
    return artifact_path


def _whitelist_from_dataset(dataset_dir: Path) -> list[str]:
    """The whitelist is embedded in every example's own prompt text (MTR-5) rather
    than stored separately -- extracted here from the first training example so
    evaluate()'s live-model comparison uses the exact same whitelist curate.py
    used, not a freshly re-queried one that could have drifted (e.g. a category
    renamed between curation and training)."""
    first_line = (dataset_dir / "train.jsonl").read_text().splitlines()[0]
    prompt = json.loads(first_line)["messages"][0]["content"]
    categories_line = next(line for line in prompt.splitlines() if line.startswith("Categories: "))
    return [name.strip() for name in categories_line.removeprefix("Categories: ").split(",")]


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune the categorization model via mlx-tune.")
    parser.add_argument("--dataset-dir", type=Path, default=Path("dataset"))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--steps", type=int, required=True, help="Required -- no silent default (MTR-6)")
    parser.add_argument("--lora-rank", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--save-format", choices=["lora_adapter"], default="lora_adapter")
    args = parser.parse_args()

    config = TrainingConfig(
        lora_rank=args.lora_rank, lora_alpha=args.lora_alpha,
        learning_rate=args.learning_rate, steps=args.steps, save_format=args.save_format,
    )
    result = train(args.dataset_dir, args.output_dir, config)
    print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    assert settings.openrouter_api_key  # fail loud before any slow model download if config is missing
    main()
