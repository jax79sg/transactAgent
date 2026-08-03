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

## Resolved Gap (Google OAuth Connection Mechanism)

Resolved as: standard web-app OAuth UX via Unit 2 (`/drive/connect` redirects the browser to Google, `/drive/callback` completes the handshake and stores the refresh token). Unit 3 only ever *reads* the stored token from the shared database — it never runs an interactive flow itself. See audit.md 2026-08-01 for the full retroactive-addition history (new `OAuthCredential` entity in Unit 1, new `drive_connect` module in Unit 2).
