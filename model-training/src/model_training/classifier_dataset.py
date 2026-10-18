"""Classifier Dataset Exporter. CLI: `python -m model_training.classifier_dataset`.

Joins every transaction (Postgres) with its stored embedding (Qdrant) and its assigned category, and writes one
Parquet file a classifier can train on, plus a manifest that says exactly what is in it and what is not.

Decisions that are easy to get wrong, made once here:

* Nothing is silently filtered. Every row keeps `label_source` (manual / similarity / llm), so the trainer chooses
  how far to trust each; rows that cannot be used (no vector, UNSURE) are counted in the manifest, not hidden.
* The split is by description, not by row. The same merchant appears hundreds of times (one description is 19% of
  this user's data), so a random row split puts copies of every training example into the test set and the
  accuracy it reports is mostly memorisation. Rows whose descriptions normalise to the same text never cross
  splits, and a description that repeats `max_eval_group_rows` times or more is trained on only, because one
  trivial pattern would otherwise be a fifth of the test set.
* The split is a pure function of (seed, description), so it does not change when more transactions arrive; a
  retrain on a bigger export evaluates on the same held-out merchants it did before.
* The vectors are the ones the live system itself uses (the worker's categorisation reads the same collection),
  written exactly as Qdrant returns them. The files hold real bank transactions, so the exporter refuses to write
  anywhere git would not ignore.

Fails loudly rather than degrading (a database error, an unreachable Qdrant, a mixed vector size): this is a
manually run, single-operator tool, like curate.py.
"""

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from array import array
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from model_training import repository
from model_training.config import settings

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "classifier-dataset"  # `data/` is git-ignored
DEFAULT_QDRANT_URL = "http://localhost:6333"
EMBEDDING_COLLECTION = "transactions"
UNSURE_NAME = "UNSURE"
SPLITS = ("train", "val", "test")
DATASET_FILE = "dataset.parquet"
MANIFEST_FILE = "manifest.json"

# What the live system embeds, for the manifest (ingestion_worker/embedding/text.py and client.py). Qdrant stores no
# model name, so the model is declared by the operator; verify it with a re-embed comparison before trusting it.
EMBEDDING_TEXT_FORMAT = "<task prefix><description minus reference noise> | <price bucket of the amount> | <inflow|outflow>"
GEMINI_TASK_PREFIX = "task: classification | query: "

# Only used to group near-identical descriptions for the split. Same patterns as ingestion_worker/embedding/text.py
# (reference codes after OTHR-/REF:, kept for PayNow-Mobile notes; the "Card Payment" phrase). If they drift from
# the worker's, the only effect is slightly different grouping; labels and vectors never depend on them.
_REFERENCE_NOISE = re.compile(r"(OTHR\s*-\s*|REF:).*$", re.IGNORECASE)
_PAYNOW_MOBILE = re.compile(r"paynow-mobile", re.IGNORECASE)
_BOILERPLATE = re.compile(r"\bcard payment\b", re.IGNORECASE)


# --------------------------------------------------------------------------------------------------- splitting


@dataclass(frozen=True)
class SplitPolicy:
    seed: int = 0
    val_fraction: float = 0.15
    test_fraction: float = 0.15
    # A description repeated at least this many times is trained on only (see the module docstring).
    max_eval_group_rows: int = 50
    # A category with fewer validation or test rows than this is listed as thinly measured.
    min_eval_rows: int = 5
    # Cross-validation folds, by description, for the categories too small to hold out in a single split.
    folds: int = 5

    def __post_init__(self) -> None:
        if not (0 <= self.val_fraction < 1 and 0 <= self.test_fraction < 1 and self.val_fraction + self.test_fraction < 1):
            raise ValueError("val_fraction and test_fraction must be in [0, 1) and sum to less than 1")
        if self.max_eval_group_rows < 1:
            raise ValueError("max_eval_group_rows must be at least 1")
        if self.folds < 2:
            raise ValueError("folds must be at least 2")


def group_key(description: str) -> str:
    """Descriptions that differ only by case, spacing, a trailing reference code or the Card Payment boilerplate are
    the same merchant, so they share a key and therefore a split."""
    text = description if _PAYNOW_MOBILE.search(description) else _REFERENCE_NOISE.sub("", description)
    text = _BOILERPLATE.sub("", text)
    return " ".join(text.lower().split()) or " ".join(description.lower().split()) or "<empty>"


def _unit_interval(seed: int, group: str) -> float:
    digest = hashlib.sha256(f"{seed}|{group}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def assign_split(group: str, group_rows: int, policy: SplitPolicy) -> str:
    """A pure function of the policy, the group and whether it is a dominant group: independent of every other row,
    so adding data never moves an existing description to a different split (except one that grows past the
    dominant-group size, which moves to train)."""
    if group_rows >= policy.max_eval_group_rows:
        return "train"
    position = _unit_interval(policy.seed, group)
    if position < policy.val_fraction:
        return "val"
    if position < policy.val_fraction + policy.test_fraction:
        return "test"
    return "train"


def assign_fold(group: str, policy: SplitPolicy) -> int:
    """Grouped cross-validation fold (0 .. folds-1): a pure function of the seed and the description, like the split. Rows
    of one description share a fold, so a model trained on the other folds has never seen that merchant."""
    return min(int(_unit_interval(policy.seed, f"fold|{group}") * policy.folds), policy.folds - 1)


# ----------------------------------------------------------------------------------------------- embeddings


def fetch_embeddings(
    base_url: str, collection: str = EMBEDDING_COLLECTION, *, page_size: int = 256, timeout: float = 30.0
) -> dict[str, list[float]]:
    """Every point of the collection as {point id: vector}, by scrolling Qdrant's REST API (standard library only).
    Raises on any error; unlike the app's own client this tool must not quietly return a partial set."""
    url = f"{base_url.rstrip('/')}/collections/{collection}/points/scroll"
    vectors: dict[str, list[float]] = {}
    offset = None
    while True:
        body: dict = {"limit": page_size, "with_payload": False, "with_vector": True}
        if offset is not None:
            body["offset"] = offset
        request = Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=timeout) as response:
            result = json.load(response)["result"]
        for point in result["points"]:
            vector = point["vector"]
            if not isinstance(vector, list):
                raise ValueError(f"point {point['id']} has a {type(vector).__name__} vector; only one unnamed vector is supported")
            vectors[str(point["id"])] = vector
        offset = result.get("next_page_offset")
        if offset is None:
            return vectors


# --------------------------------------------------------------------------------------------------- building


@dataclass
class DatasetBuild:
    rows: list[dict]
    dimensions: int
    stats: dict


def build_dataset(
    transactions: Sequence[repository.LabelledTransaction], vectors: dict[str, list[float]], policy: SplitPolicy
) -> DatasetBuild:
    """Pure: the same inputs always give the same rows, in transaction-id order."""
    usable = [t for t in transactions if t.category_name != UNSURE_NAME and str(t.transaction_id) in vectors]
    excluded_unsure = sum(1 for t in transactions if t.category_name == UNSURE_NAME)
    excluded_no_vector = sum(1 for t in transactions if t.category_name != UNSURE_NAME and str(t.transaction_id) not in vectors)
    known_ids = {str(t.transaction_id) for t in transactions}
    orphan_vectors = sum(1 for point_id in vectors if point_id not in known_ids)
    if not usable:
        raise ValueError("no transaction has both a usable category and an embedding; nothing to export")

    sizes = {len(vectors[str(t.transaction_id)]) for t in usable}
    if len(sizes) != 1:
        raise ValueError(f"the embeddings do not all have the same size: {sorted(sizes)}")
    dimensions = sizes.pop()
    norms = []
    for t in usable:
        vector = vectors[str(t.transaction_id)]
        if not all(math.isfinite(x) for x in vector):
            raise ValueError(f"the embedding of transaction {t.transaction_id} has a non-finite value")
        norms.append(math.sqrt(sum(x * x for x in vector)))

    usable.sort(key=lambda t: str(t.transaction_id))
    groups = [group_key(t.description) for t in usable]
    group_rows = Counter(groups)
    group_categories: dict[str, set[str]] = defaultdict(set)
    for t, g in zip(usable, groups, strict=True):
        group_categories[g].add(t.category_name)

    rows = []
    for t, g in zip(usable, groups, strict=True):
        outflow = t.out_flow is not None
        amount = t.out_flow if outflow else t.in_flow
        rows.append(
            {
                "transaction_id": str(t.transaction_id),
                "transaction_date": t.transaction_date,
                "description": t.description,
                "direction": "outflow" if outflow else "inflow",
                "amount": float(amount) if amount is not None else None,
                "currency": t.currency,
                "converted_amount_sgd": float(t.converted_amount_sgd) if t.converted_amount_sgd is not None else None,
                "conversion_is_approximate": t.conversion_is_approximate,
                "conversion_unavailable": t.conversion_unavailable,
                "bank_name": t.bank_name,
                "bank_statement_id": str(t.bank_statement_id),
                "statement_account_id": str(t.statement_account_id) if t.statement_account_id else None,
                "category": t.category_name,
                "category_id": str(t.category_id),
                "label_source": t.category_source.value,
                "llm_suggested_category": t.llm_suggested_category_name,
                "label_conflict": len(group_categories[g]) > 1,
                "group": g,
                "group_rows": group_rows[g],
                "split": assign_split(g, group_rows[g], policy),
                "fold": assign_fold(g, policy),
                "embedding": vectors[str(t.transaction_id)],
            }
        )

    return DatasetBuild(rows=rows, dimensions=dimensions, stats=_stats(rows, policy, {
        "transactions_read": len(transactions),
        "excluded_unsure": excluded_unsure,
        "excluded_no_vector": excluded_no_vector,
        "vectors_without_a_transaction": orphan_vectors,
        "embedding_norm_min": min(norms),
        "embedding_norm_max": max(norms),
    }))


def _stats(rows: list[dict], policy: SplitPolicy, counts: dict) -> dict:
    per_category: dict[str, Counter] = defaultdict(Counter)
    descriptions: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        per_category[row["category"]][row["split"]] += 1
        descriptions[row["category"]].add(row["group"])
    absent = sorted(c for c, n in per_category.items() if n["val"] == 0 or n["test"] == 0)
    thin = sorted(
        c for c, n in per_category.items() if c not in absent and (n["val"] < policy.min_eval_rows or n["test"] < policy.min_eval_rows)
    )
    group_rows = Counter(row["group"] for row in rows)
    dominant = {g: n for g, n in group_rows.items() if n >= policy.max_eval_group_rows}
    return {
        **counts,
        "rows_written": len(rows),
        "classes": len(per_category),
        "rows_by_split": {s: sum(1 for r in rows if r["split"] == s) for s in SPLITS},
        "groups_by_split": {s: len({r["group"] for r in rows if r["split"] == s}) for s in SPLITS},
        "rows_by_label_source": dict(sorted(Counter(r["label_source"] for r in rows).items())),
        "rows_by_category": {
            c: {"total": sum(n.values()), **{s: n[s] for s in SPLITS}, "descriptions": len(descriptions[c])}
            for c, n in sorted(per_category.items())
        },
        "label_conflict_rows": sum(1 for r in rows if r["label_conflict"]),
        "dominant_groups": {"groups": len(dominant), "rows": sum(dominant.values())},
        "categories_missing_from_val_or_test": absent,
        "categories_with_fewer_than_3_descriptions": sorted(c for c, d in descriptions.items() if len(d) < 3),
        "categories_thinly_measured": thin,
    }


# ----------------------------------------------------------------------------------------------------- writing


def _schema(dimensions: int) -> pa.Schema:
    return pa.schema(
        [
            ("transaction_id", pa.string()),
            ("transaction_date", pa.date32()),
            ("description", pa.string()),
            ("direction", pa.string()),
            ("amount", pa.float64()),
            ("currency", pa.string()),
            ("converted_amount_sgd", pa.float64()),
            ("conversion_is_approximate", pa.bool_()),
            ("conversion_unavailable", pa.bool_()),
            ("bank_name", pa.string()),
            ("bank_statement_id", pa.string()),
            ("statement_account_id", pa.string()),
            ("category", pa.string()),
            ("category_id", pa.string()),
            ("label_source", pa.string()),
            ("llm_suggested_category", pa.string()),
            ("label_conflict", pa.bool_()),
            ("group", pa.string()),
            ("group_rows", pa.int32()),
            ("split", pa.string()),
            ("fold", pa.int32()),
            ("embedding", pa.list_(pa.float32(), dimensions)),
        ]
    )


def content_hash(rows: list[dict]) -> str:
    """Identifies the data itself (ids, labels, splits and vector bytes), not the file or when it was made."""
    digest = hashlib.sha256()
    for row in rows:
        digest.update(f"{row['transaction_id']}|{row['category']}|{row['label_source']}|{row['split']}|{row['fold']}\n".encode())
        vector = array("f", row["embedding"])
        if sys.byteorder == "big":
            vector.byteswap()
        digest.update(vector.tobytes())
    return digest.hexdigest()


def assert_not_publishable(output_dir: Path) -> None:
    """The files hold real bank transactions. Refuse to write them anywhere a `git add` would pick up (the repository
    is public); outside any git repository, or inside an ignored path, is fine."""
    anchor = output_dir.resolve()
    while not anchor.exists():
        anchor = anchor.parent
    probe = output_dir.resolve() / DATASET_FILE
    inside = subprocess.run(["git", "-C", str(anchor), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True, check=False)
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return
    ignored = subprocess.run(["git", "-C", str(anchor), "check-ignore", "-q", "--", str(probe)], capture_output=True, check=False)
    if ignored.returncode != 0:
        raise SystemExit(
            f"Refusing to write {probe}: it is inside a git repository and not ignored, and this file holds real bank "
            "transactions. Use a path under the repository's git-ignored data/ folder, or outside the repository."
        )


def write_dataset(
    build: DatasetBuild, output_dir: Path, *, source: dict, embedding_model: str, policy: SplitPolicy
) -> dict:
    assert_not_publishable(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    columns = {name: [row[name] for row in build.rows] for name in _schema(build.dimensions).names}
    table = pa.Table.from_pydict(columns, schema=_schema(build.dimensions))
    pq.write_table(table, output_dir / DATASET_FILE, compression="zstd")

    content = content_hash(build.rows)
    dataset_file = output_dir / DATASET_FILE
    manifest = {
        "dataset_id": f"clf-{content[:12]}",
        "content_sha256": content,
        "created_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": {
            DATASET_FILE: {"bytes": dataset_file.stat().st_size, "sha256": hashlib.sha256(dataset_file.read_bytes()).hexdigest()}
        },
        "source": source,
        "embedding": {
            "model_declared": embedding_model,
            "task_prefix": GEMINI_TASK_PREFIX,
            "text_format": EMBEDDING_TEXT_FORMAT,
            "dimensions": build.dimensions,
            "distance": "cosine",
            "note": "Vectors are exactly as Qdrant returns them (Qdrant normalises cosine vectors to unit length). The "
            "model name is declared by the operator, not read from Qdrant.",
        },
        "columns": {
            "label": "category",
            "label_source": "manual = set or confirmed by a person; similarity = copied from a similar earlier transaction; "
            "llm = chosen by the language model. Not equally trustworthy.",
            "llm_suggested_category": "The language model's first-pass suggestion, kept for comparison. Do NOT use it as a feature.",
            "fold": "Grouped cross-validation fold; rows of one description share a fold.",
            "group_rows": "How many rows share this description. A few merchants repeat hundreds of times, so weight rows by "
            "1/group_rows (or leave out rows at or above max_eval_group_rows) for a score that is not dominated by them.",
            "label_conflict": "True when descriptions that normalise to the same text carry more than one category in the data.",
            "embedding": "float32 vector; the same one the live system's similarity search uses.",
        },
        "split_policy": asdict(policy),
        "split_rule": "split = f(seed, normalised description) only; a description repeated max_eval_group_rows times or more is "
        "train-only. Rows of one description never cross splits. fold = f(seed, description) as well, for grouped "
        "cross-validation (train on the other folds); use it for categories the single split cannot measure.",
        "stats": build.stats,
    }
    (output_dir / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    return manifest


# ------------------------------------------------------------------------------------------------------- CLI


def _summary(manifest: dict, output_dir: Path) -> str:
    s = manifest["stats"]
    lines = [
        f"dataset {manifest['dataset_id']}  ->  {output_dir}",
        f"  rows written {s['rows_written']} of {s['transactions_read']} read "
        f"(UNSURE excluded {s['excluded_unsure']}, no vector {s['excluded_no_vector']}, "
        f"vectors without a transaction {s['vectors_without_a_transaction']})",
        f"  embedding: {manifest['embedding']['dimensions']} dimensions, norm {s['embedding_norm_min']:.4f} to {s['embedding_norm_max']:.4f}",
        f"  classes {s['classes']}; label source {s['rows_by_label_source']}",
        f"  rows by split {s['rows_by_split']}; descriptions by split {s['groups_by_split']}",
        f"  train-only dominant descriptions: {s['dominant_groups']['groups']} covering {s['dominant_groups']['rows']} rows",
        f"  rows whose description carries more than one category: {s['label_conflict_rows']}",
    ]
    if s["categories_missing_from_val_or_test"]:
        lines.append(f"  NOT measurable (absent from validation or test): {', '.join(s['categories_missing_from_val_or_test'])}")
    if s["categories_with_fewer_than_3_descriptions"]:
        lines.append(f"  fewer than 3 distinct descriptions (cannot be held out without leakage): {', '.join(s['categories_with_fewer_than_3_descriptions'])}")
    if s["categories_thinly_measured"]:
        lines.append(f"  thinly measured (< {manifest['split_policy']['min_eval_rows']} rows in validation or test): {', '.join(s['categories_thinly_measured'])}")
    return "\n".join(lines)


def export_dataset(
    db: Session, qdrant_url: str, output_dir: Path | None, policy: SplitPolicy, embedding_model: str, *, database: str = "postgres"
) -> tuple[dict, Path]:
    """Read, join, split and write. Returns the manifest and the folder written."""
    transactions = repository.list_labelled_transactions(db)
    vectors = fetch_embeddings(qdrant_url)
    build = build_dataset(transactions, vectors, policy)
    output_dir = output_dir or DEFAULT_OUTPUT_ROOT / f"clf-{content_hash(build.rows)[:12]}"
    source = {"database": database, "vectors": f"{qdrant_url} / {EMBEDDING_COLLECTION}"}
    return write_dataset(build, output_dir, source=source, embedding_model=embedding_model, policy=policy), output_dir


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Export every transaction, its embedding and its category as a classifier dataset.")
    parser.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL", DEFAULT_QDRANT_URL),
                        help="Qdrant REST address (not published to the host by default; on OrbStack use http://transactagent-vector-db.orb.local:6333)")
    parser.add_argument("--output-dir", type=Path, default=None, help="default: data/classifier-dataset/<dataset id> under the repository")
    parser.add_argument("--embedding-model", default="gemini-embedding-2", help="the model that made the stored vectors (declared, not detected)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--val-fraction", type=float, default=0.15)
    parser.add_argument("--test-fraction", type=float, default=0.15)
    parser.add_argument("--max-eval-group-rows", type=int, default=50)
    parser.add_argument("--min-eval-rows", type=int, default=5)
    parser.add_argument("--folds", type=int, default=5, help="grouped cross-validation folds")
    args = parser.parse_args(argv)
    policy = SplitPolicy(args.seed, args.val_fraction, args.test_fraction, args.max_eval_group_rows, args.min_eval_rows, args.folds)

    engine = create_engine(settings.database_url)
    with Session(engine) as db:
        manifest, output_dir = export_dataset(
            db, args.qdrant_url, args.output_dir, policy, args.embedding_model,
            database=f"postgres {settings.db_host}:{settings.db_port}/{settings.db_name}",
        )
    print(_summary(manifest, output_dir))


if __name__ == "__main__":
    main()
