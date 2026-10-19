# Performance Test Instructions

## Status: N/A (documented, not skipped silently)

Formal performance/load testing is not applicable to this project, consistent with every NFR Requirements stage across all 4 units:

- **Single personal user** — this app was never designed for concurrent load; requirements.md explicitly scopes it to one user on their own machine
- **No performance NFR targets were ever set** — each unit's `nfr-requirements.md` assessed Performance as "no hard target," relying on Unit 1's indexing strategy and standard framework defaults rather than a measured budget
- **Resiliency Baseline extension opted out** (requirements.md NFR-5.3) — the extension that would normally drive load/capacity planning was declined at Requirements Analysis

## What Was Actually Verified Instead

Rather than formal load testing, the Build and Test stage verified real responsiveness qualitatively:
- API responses (`/health`, `/categories`, dashboard endpoints) returned promptly (sub-second) against a near-empty database during manual `curl` verification
- The frontend's dashboard/transaction pages rendered without perceptible lag in a real browser session

## If Load Testing Ever Becomes Relevant

Should this app's scope ever grow beyond personal use (e.g., NFR-1.2's "future cloud deployment" consideration becoming concrete), a reasonable starting point would be:
- `k6` or `locust` against Unit 2's REST API, focused on the `GET /transactions` and `GET /dashboards/*` endpoints (the only ones with real aggregation work), using the indexing strategy already documented in Unit 1's `nfr-requirements.md` as the baseline to validate
- No such tooling is included in this codebase — this is a note for future scope, not a current deliverable

---

## Addendum (2026-10-04) — Probable Duplicate Statement Detection (Epic 14)

The only new computation with a size dependency is the matching rule (`ingestion_worker/duplicates/matching.py`). Measured on the development machine, in the worker's environment:

| Case | Time |
|---|---|
| Two 300-transaction copies, all distinct keys | 0.7 ms |
| 40 same-key transactions per side, every description different (worst plausible fuzzy case) | 25 ms |
| A whole pair scan: 200 statements (4 banks × 50), 30 transactions each, 4,900 overlapping pairs | 0.12 s |
| Dense group, similar descriptions: 200 / 600 / 1,100 same-key transactions per side | 0.3 s / 2.9 s / recursion limit exceeded after ~10 s |

The last row is a known bound, not a defect in practice: it needs about 1,100 transactions with the same date, amount, direction and currency in one statement. Real statements average 39 transactions (172 statements, 6,667 transactions). On a breach the ingestion check fails open and a failed scan is logged and retried without blocking other work. If real data ever approaches it, make the pairing iterative or cap the fuzzy stage for very large groups (fewer matches can only lower a ratio, so the safe direction).

Re-measure by timing `matching.evaluate` (or `match_transactions`) on synthetic `StatementSide` pairs of the shapes in the table; no load-testing tooling is needed for a one-user app.
