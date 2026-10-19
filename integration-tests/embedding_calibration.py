"""Calibrate an embedding model's similarity thresholds on your OWN labelled transactions (a re-usable tool; read-only).

WHEN: before switching `embedding_provider` / the embedding model, because cosine scores sit on a different scale for each
model, so `embedding_similarity_threshold` and `recategorization_auto_apply_threshold` must be re-chosen for it.

WHAT IT DOES: embeds every unique transaction text (built with the worker's real `build_embedding_text`), finds each
transaction's nearest neighbour among the others, and reports -- per cosine threshold -- how many have a neighbour above it
(coverage) and how often that neighbour has the same category (precision), for neighbours with ANY description and with a
DIFFERENT description (the case where embeddings add value over exact matching). It compares the text as the worker builds
it with the recommended Gemini task prefix, and prints fuzzy-text matching for context.

HOW: export your labelled transactions to <dir>/labelled.csv (columns description, amount, direction [outflow|inflow],
category, source), e.g. from the live database:
    docker exec transactagent-db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "copy (select t.description,
      coalesce(t.out_flow,t.in_flow) as amount, case when t.out_flow is not null then \'outflow\' else \'inflow\' end as
      direction, c.name as category, t.category_source::text as source from transactions t join categories c on
      c.id=t.category_id) to stdout with csv header"' > <dir>/labelled.csv
then run it inside the worker image (it has the real text builder and your key):
    docker compose run --rm -T -v <dir>:/out -v $PWD/integration-tests/embedding_calibration.py:/out/calibrate.py \\
        ingestion-worker python -W ignore /out/calibrate.py gemini-embedding-2
Labels that were themselves produced by similarity matching flatter every model's precision, so read the numbers
as a comparison between settings, not as an absolute accuracy; the `manual` column is the harder, more trustworthy one.
Calls the embeddings API (a few cents for ~7,000 transactions). Results are cached in <dir> and written to
<dir>/calibration_results.json.
"""
import csv
import hashlib
import json
import logging
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import numpy as np
from openai import OpenAI

logging.disable(logging.CRITICAL)
from ingestion_worker import config  # noqa: E402
from ingestion_worker.embedding.text import build_embedding_text  # noqa: E402

MODEL = sys.argv[1] if len(sys.argv) > 1 else "gemini-embedding-2"
DIMS = 768
client = OpenAI(api_key=config.settings.gemini_api_key, base_url="https://generativelanguage.googleapis.com/v1beta/openai/", timeout=60)

rows = [r for r in csv.DictReader(open("/out/labelled.csv")) if r["source"] != "unsure"]
for r in rows:
    r["text"] = build_embedding_text(r["description"], Decimal(r["amount"]), r["direction"])
print(f"{len(rows)} labelled transactions, {len({r['text'] for r in rows})} unique embedding texts, model={MODEL}, dims={DIMS}")


def embed_texts(texts, tag):
    key = hashlib.sha1((MODEL + tag + "|".join(texts)).encode()).hexdigest()[:12]
    path = f"/out/emb_{key}.npy"
    try:
        return np.load(path)
    except FileNotFoundError:
        pass
    batches = [texts[i:i + 64] for i in range(0, len(texts), 64)]

    def one(batch):
        for attempt in range(6):
            try:
                r = client.embeddings.create(model=MODEL, input=batch, dimensions=DIMS)
                assert len(r.data) == len(batch), (len(r.data), len(batch))
                return [d.embedding for d in r.data]  # the compat layer sets no index: order is the input order (verified below)
            except Exception as e:  # noqa: BLE001
                time.sleep(2 ** attempt)
                err = e
        raise err

    t = time.time()
    with ThreadPoolExecutor(max_workers=4) as ex:
        out = [v for vs in ex.map(one, batches) for v in vs]
    arr = np.array(out, dtype=np.float32)
    # verify batch order == input order: three texts embedded ALONE must equal their batched vectors
    for i in (0, len(texts) // 2, len(texts) - 1):
        solo = np.array(client.embeddings.create(model=MODEL, input=texts[i], dimensions=DIMS).data[0].embedding, dtype=np.float32)
        cos = float(solo @ arr[i] / (np.linalg.norm(solo) * np.linalg.norm(arr[i])))
        assert cos > 0.999, f"batch order mismatch at {i}: cosine {cos}"
    print(f"  embedded {len(texts)} texts [{tag}] in {time.time() - t:.0f}s -> {arr.shape}")
    np.save(path, arr)
    return arr


uniq = sorted({r["text"] for r in rows})
pos = {t: i for i, t in enumerate(uniq)}
idx = np.array([pos[r["text"]] for r in rows])
labels = np.array([r["category"] for r in rows])
descs = np.array([r["description"] for r in rows])
manual = np.array([r["source"] == "manual" for r in rows])
n = len(rows)
THR = [0.60, 0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.92, 0.94, 0.95, 0.96, 0.97, 0.98, 0.99]


def analyse(E, name):
    E = E / np.linalg.norm(E, axis=1, keepdims=True)
    X = E[idx]
    S = X @ X.T
    np.fill_diagonal(S, -1.0)  # not itself
    res = {"name": name}
    for mode in ("any", "different_description"):
        M = S.copy()
        if mode == "different_description":
            # drop neighbours whose DESCRIPTION is identical (exact matches are trivial); same text with a different amount bucket
            # is a different embedding text but the same description, so compare descriptions, not texts
            same = descs[:, None] == descs[None, :]
            M[same] = -1.0
        j = M.argmax(axis=1)
        s = M[np.arange(n), j]
        ok = labels[j] == labels
        rows_out = []
        for t in THR:
            sel = s >= t
            cov = sel.mean()
            prec = ok[sel].mean() if sel.any() else float("nan")
            mprec = ok[sel & manual].mean() if (sel & manual).any() else float("nan")
            rows_out.append((t, round(100 * cov, 1), round(100 * prec, 1), round(100 * mprec, 1), int(sel.sum())))
        res[mode] = rows_out
        res[mode + "_median_top1_score"] = round(float(np.median(s)), 3)
    return res


def show(res):
    print(f"\n=== {res['name']}")
    for mode in ("any", "different_description"):
        print(f"  nearest neighbour, {mode.replace('_', ' ')} (median top-1 cosine {res[mode + '_median_top1_score']}):")
        print("    cosine>=   coverage%  precision%  precision%(manual items)   n")
        for t, cov, prec, mprec, k in res[mode]:
            print(f"    {t:<9}  {cov:>8}  {prec:>10}  {mprec:>22}  {k:>6}")


results = []
E_raw = embed_texts(uniq, "raw")
results.append(analyse(E_raw, "gemini-embedding-2, text as the worker builds it"))
E_pref = embed_texts(["task: classification | query: " + t for t in uniq], "classification_prefix")
results.append(analyse(E_pref, "gemini-embedding-2, with the recommended 'task: classification | query: ' prefix"))
for r in results:
    show(r)
json.dump(results, open("/out/calibration_results.json", "w"))

# context: the other matching path in the pipeline, fuzzy text (rapidfuzz token_sort_ratio), nearest neighbour, different description
try:
    from rapidfuzz import fuzz, process
    ud = sorted(set(descs))
    dpos = {d: i for i, d in enumerate(ud)}
    cd = process.cdist(ud, ud, scorer=fuzz.token_sort_ratio, workers=2)
    np.fill_diagonal(cd, -1)
    drow = np.array([dpos[d] for d in descs])
    best = cd[drow].argmax(axis=1)  # neighbour DESCRIPTION index (excludes same description by construction of the diagonal)
    sc = cd[drow, best]
    # label of the neighbour: the most common label among rows with that description
    by_desc = {}
    for d, l in zip(descs, labels):
        by_desc.setdefault(d, Counter())[l] += 1
    nlab = np.array([by_desc[ud[b]].most_common(1)[0][0] for b in best])
    ok = nlab == labels
    print("\n=== context: fuzzy-text matching (rapidfuzz token_sort_ratio), nearest DIFFERENT description")
    print("    score>=   coverage%  precision%")
    for t in (60, 70, 80, 85, 90, 95):
        sel = sc >= t
        print(f"    {t:<8}  {100 * sel.mean():>8.1f}  {100 * ok[sel].mean():>10.1f}")
except Exception as e:  # noqa: BLE001
    print("fuzzy context skipped:", e)
