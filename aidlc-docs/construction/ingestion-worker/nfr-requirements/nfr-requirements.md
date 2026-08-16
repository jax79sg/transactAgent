# NFR Requirements — Unit 3: Ingestion Worker Service

## Assessed Categories

| Category | Requirement | Rationale |
|---|---|---|
| Scalability | No target | Single personal user, one worker process |
| Performance | No hard target beyond inherent LLM API latency | Personal, manually-triggered workflow |
| Availability | No SLA | Resiliency Baseline extension opted out |
| Security | Gemini/OpenRouter API keys, DB credentials via env vars (NFR-4.1); Drive refresh token read from `oauth_credentials` (Unit 1), written there by Unit 2's OAuth flow (retroactive addition, see audit.md) | Consistent with NFR-4.1 across all units |
| Reliability | WR-1/WR-7 (no cross-provider retry, terminal failure) | Already captured in Functional Design |
| Maintainability | PBT framework: **Hypothesis**, applied to the similarity-matching function, currency-conversion source-priority resolver, and extraction-response schema validation round-trip | Partial PBT mode (requirements.md NFR-5.2) |
| Usability | N/A | No UI in this unit |

## Tech Stack Decisions (Summary — see tech-stack-decisions.md)

- **Google Drive SDK**: `google-api-python-client` + `google-auth` (reads the refresh token from `oauth_credentials`, refreshes access tokens as needed)
- **Extraction LLM**: Google Gemini via `google-genai` (vision/PDF input)
- **Categorization LLM fallback**: OpenRouter free-tier model via the `openai` package pointed at OpenRouter's `base_url`
- **PDF-to-image**: `pdf2image` (+ `poppler-utils` system package in the Docker image)
- **Similarity matching**: `rapidfuzz`
- **PBT**: `hypothesis`
- **Worker loop**: 5-second polling interval

## Addendum (2026-08-13, Local Embedding-Based Semantic Similarity feature — Epic 9)

| Category | Requirement | Rationale |
|---|---|---|
| Scalability | No target — same as base unit | Vector DB volume tracks transaction volume, still personal-scale |
| Performance | Embedding calls are soft-dependency, non-blocking (FR-10); no hard latency target | Matches base unit's LLM-latency framing |
| Availability | No SLA; embedding endpoint (oMLX) is an explicitly optional, user-managed dependency (NFR-5) | FR-10's soft-fail design means the whole feature degrades gracefully, never blocks ingestion |
| Security | No new secret — oMLX endpoint is host-local, no auth assumed by default; Qdrant has no auth enabled by default at this scale (internal-network-only, no host port) | Consistent with this project's opted-out Security Baseline extension |
| Reliability | WR-25: no retry, immediate soft-fail on any embedding-path error — diverges from the Drive/Backup retry-with-backoff pattern on purpose | See `nfr-design-patterns.md` addendum |
| Maintainability | New pure/testable logic split out per NFR-3 of the requirements (e.g. top-K post-filter selection) gets Hypothesis PBT coverage where applicable; the embedding HTTP call itself and the Qdrant client calls are explicitly out of PBT scope (I/O-bound) | NFR-3 |
| Usability | N/A | No UI in this unit |

**Tech stack additions**: Vector DB **Qdrant** (`qdrant-client` Python SDK); embedding endpoint client via `httpx` against a new, separately-configured oMLX instance (`EMBEDDING_BASE_URL`/`EMBEDDING_MODEL`, distinct from the existing `OPENROUTER_*` oMLX instance already in use for categorization-LLM-fallback text generation). New tunables: `EMBEDDING_SIMILARITY_THRESHOLD` (0.75 default, cosine scale), `EMBEDDING_TOP_K` (5), `EMBEDDING_BATCH_SIZE` (50), `EMBEDDING_DIMENSIONS` (768). See `tech-stack-decisions.md` for full rationale.

## Resolved Gap (Google OAuth Connection Mechanism)

Resolved as: standard web-app OAuth UX via Unit 2 (`/drive/connect` redirects the browser to Google, `/drive/callback` completes the handshake and stores the refresh token). Unit 3 only ever *reads* the stored token from the shared database — it never runs an interactive flow itself. See audit.md 2026-08-01 for the full retroactive-addition history (new `OAuthCredential` entity in Unit 1, new `drive_connect` module in Unit 2).
