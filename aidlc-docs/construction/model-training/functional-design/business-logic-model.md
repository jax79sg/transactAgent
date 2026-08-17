# Business Logic Model — Model Training Unit

## Dataset Curator Component

```
curateDataset(outputDir, trainSplitRatio=0.85):
  eligible = query eligible transactions (MTR-1)
    join categories for category_name
  breakdown = count eligible by category_source

  usable, excluded_null = partition eligible on converted_amount_sgd IS NOT NULL   [MTR-2]

  examples = [TrainingExample(transaction_id, description, amount_sgd, category_name)
              for each row in usable]                                              [no dedup, MTR-3]

  sorted_examples = sort examples by transaction_id                                [MTR-4, determinism]
  split_index = floor(len(sorted_examples) * trainSplitRatio)
  train, val = sorted_examples[:split_index], sorted_examples[split_index:]

  whitelist = query active category names (excluding "UNSURE")

  write train -> outputDir/train.jsonl                                            [MTR-5 chat format]
  write val   -> outputDir/val.jsonl

  summary = CurationSummary(
    train_count=len(train), val_count=len(val),
    source_breakdown=breakdown, excluded_null_amount_count=len(excluded_null))
  print(summary)                                                                   [console, for the
                                                                                      operator running
                                                                                      this manually]
  return summary
```

No ClearML involvement here — dataset curation is a pure DB-to-disk step; ClearML tracking starts with the training run (FR-CFT-6 scopes it to `train()`, not `curate`).

## Fine-Tuning Trainer Component

```
train(datasetDir, config):
  task = ClearML.init(project="transactagent-categorization-finetuning",
                       task_name=f"finetune-{now_iso8601()}")                      [MTR-9]
  task.connect(config)                                                             [logs hyperparameters]

  # CORRECTION (found at Code Generation, see note below the pseudocode block):
  # Gemma 4 is a VLM even for text-only tasks -- FastVisionModel/VLMSFTTrainer/
  # VLMSFTConfig are required, not the plain FastLanguageModel/SFTTrainer path
  # this pseudocode originally showed.
  model, processor = mlx_tune.FastVisionModel.from_pretrained(
      "mlx-community/gemma-4-26b-a4b-it-4bit", load_in_4bit=True)
  model = mlx_tune.FastVisionModel.get_peft_model(
      model, finetune_vision_layers=False, finetune_language_layers=True,
      finetune_attention_modules=True, finetune_mlp_modules=True,
      r=config.lora_rank, lora_alpha=config.lora_alpha,
      lora_dropout=0, bias="none", random_state=3407)                             [MTR-6 defaults]

  # Each example's message `content` is a list of {"type": "text", "text": ...}
  # parts (VLM shape), adapted from curate.py's plain-string JSONL at load time --
  # curate.py itself stays free of any VLM-specific/model-specific assumption.
  train_dataset = [to_vlm_messages(line) for line in read_jsonl(f"{datasetDir}/train.jsonl")]
  trainer = mlx_tune.VLMSFTTrainer(
      model=model, tokenizer=processor,
      data_collator=mlx_tune.UnslothVisionDataCollator(model, processor),
      train_dataset=train_dataset,
      args=VLMSFTConfig(
          per_device_train_batch_size=1, gradient_accumulation_steps=4,
          warmup_steps=5, max_steps=config.steps, learning_rate=config.learning_rate,
          output_dir=config.output_dir, remove_unused_columns=False,
          dataset_kwargs={"skip_prepare_dataset": True}, max_length=config.max_length))
  trainer.train()                                                                  [metrics auto-logged
                                                                                      to the active
                                                                                      ClearML task via
                                                                                      mlx-tune's own
                                                                                      training loop
                                                                                      callbacks, same as
                                                                                      any ClearML-aware
                                                                                      training script]

  FastVisionModel.for_inference(model)
  eval_result = evaluate(lambda prompt: model.generate(prompt=prompt, max_tokens=32, temperature=0),
                          f"{datasetDir}/val.jsonl", whitelist)
  task.get_logger().report_table("confusion_matrix", eval_result.confusion_matrix) [MTR-8]
  task.get_logger().report_scalar("accuracy", eval_result.accuracy)
  task.get_logger().report_scalar("agreement_with_live_model", eval_result.agreement)

  artifact_path = saveArtifact(model, config.output_dir, config.save_format)
  task.upload_artifact("model", artifact_path)                                     [FR-CFT-6: artifact
                                                                                      logged to ClearML
                                                                                      too, not just
                                                                                      saved locally]
  task.close()
  return TrainingRunResult(clearml_task_id=task.id, artifact_path=artifact_path,
                            accuracy=eval_result.accuracy,
                            agreement_with_live_model=eval_result.agreement)


evaluate(generate_fn, validationSplitPath, whitelist):
  val_examples = read_jsonl(validationSplitPath)
  correct, confusion = 0, defaultdict(Counter)
  agree = 0
  for example in val_examples:
    fine_tuned_prediction = generate_fn(example.rendered_user_prompt)              [same prompt already
                                                                                      embedded in the
                                                                                      example, MTR-5;
                                                                                      generate_fn supplied
                                                                                      by train.py so this
                                                                                      function has no
                                                                                      direct mlx_tune
                                                                                      import -- stays
                                                                                      testable without a
                                                                                      real model loaded]
    live_prediction = call_live_oMLX_server(example.description, example.amount_sgd,
                                             whitelist)                            [MTR-7: independent
                                                                                      HTTP call, same
                                                                                      prompt template,
                                                                                      NOT a call into
                                                                                      api-service/
                                                                                      ingestion-worker]
    confusion[example.category_name][fine_tuned_prediction] += 1                   [MTR-8]
    if fine_tuned_prediction == example.category_name: correct += 1
    if fine_tuned_prediction == live_prediction: agree += 1

  return EvalResult(
    accuracy=correct / len(val_examples),
    confusion_matrix=confusion,
    agreement=agree / len(val_examples))


saveArtifact(model, outputPath, format):
  if format == 'lora_adapter': model.save_pretrained(outputPath)                   [FR-CFT-8]
  else: raise NotImplementedError                                                  [mlx-tune's VLM path
                                                                                      (required for Gemma
                                                                                      4, see correction
                                                                                      below) has no
                                                                                      save_pretrained_merged
                                                                                      equivalent in the
                                                                                      examples reviewed --
                                                                                      'merged' fails loudly
                                                                                      rather than silently
                                                                                      falling back]
  return outputPath                                                                [no conversion, no
                                                                                      deployment call --
                                                                                      Resolved Decision 7]
```

## Correction Found at Code Generation: Gemma 4 Requires the VLM API Path
The pseudocode above (and this feature's earlier Application Design / Functional Design drafts) assumed mlx-tune's plain-text `FastLanguageModel`/`SFTTrainer`/`SFTConfig` path — the one shown in mlx-tune's own top-level README quick start — would apply. Actually inspecting mlx-tune's real, runnable examples (`examples/39_gemma4_text_to_sql.py`, `examples/40_gemma4_moe_finetuning.py` — both targeting this exact `gemma-4-26b-a4b-it-4bit` model family) surfaced an explicit note neither the README excerpt nor Requirements Analysis's research had caught: **"Gemma 4 models are all VLMs — use FastVisionModel even for text tasks."** `FastLanguageModel` cannot load this checkpoint correctly. Corrected throughout: `FastVisionModel.from_pretrained`/`get_peft_model` (with `finetune_vision_layers=False` for this text-only task), `VLMSFTTrainer`/`VLMSFTConfig`/`UnslothVisionDataCollator`, and every chat message's `content` as a list of `{"type": "text", "text": ...}` parts rather than a plain string. Inference for `evaluate()` uses the VLM path's own `model.generate(prompt=..., max_tokens=..., temperature=...)` (confirmed against `examples/39`), not the plain-text path's separate `mlx_lm.generate(model.model, tokenizer, ...)` helper (confirmed against `examples/03_inference.py`) — the two model families use genuinely different inference call shapes, not just different loading calls.

## Notes on Determinism vs. the Trainer's Own Randomness (flagged, not a requirements gap)
MTR-4 makes the **dataset split** deterministic, but the training run itself (LoRA weight initialization, any data-shuffling `SFTTrainer` does internally) is not claimed to be bit-for-bit reproducible — that's normal for any LLM fine-tuning tool and out of scope for NFR-CFT-4, which is about the *curated dataset* being reproducible from DB state, not about two training runs with identical config producing byte-identical model weights.
