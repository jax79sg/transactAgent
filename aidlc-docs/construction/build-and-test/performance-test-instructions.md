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
