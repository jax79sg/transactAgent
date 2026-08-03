# Unit of Work Story Map — Bank Transaction Insights App

Each of the 24 approved stories is mapped to its primary implementing unit. Where a story spans units (frontend consuming a backend capability), the **primary** unit is the one that owns the business logic/data; the Frontend SPA unit implicitly implements the UI for every story and is not re-listed as "primary" unless the story is purely presentational.

| Story | Primary Unit | Notes |
|---|---|---|
| US-1.1 Connect Google Drive | Unit 3: Ingestion Worker Service | OAuth flow initiation may be surfaced via Unit 2's API, but token storage/refresh logic lives in Unit 3 |
| US-1.2 Trigger and monitor ingestion run | Unit 2 (trigger/status) + Unit 3 (execution) | Split by design — Unit 2 owns the job record API, Unit 3 owns actually running it |
| US-1.3 Extract transactions | Unit 3: Ingestion Worker Service | |
| US-1.4 Avoid duplicate processing | Unit 3: Ingestion Worker Service | |
| US-1.5 Review ingestion history | Unit 2: API Service | Reads the same job/run records Unit 3 writes |
| US-2.1 Auto-categorize via similarity | Unit 3: Ingestion Worker Service | |
| US-2.2 Auto-categorize via LLM fallback | Unit 3: Ingestion Worker Service | |
| US-2.3 UNSURE flagging | Unit 3: Ingestion Worker Service | |
| US-3.1 Browse raw transactions | Unit 2: API Service | |
| US-3.2 Filter transactions | Unit 2: API Service | |
| US-3.3 Group transactions | Unit 2: API Service | |
| US-3.4 Manual category correction | Unit 2 (correction + job enqueue) + Unit 3 (retro recategorization job handler) | Cross-unit per FR-5.4 design decision |
| US-3.5 Find/clear UNSURE transactions | Unit 2: API Service | |
| US-3.6 Export CSV | Unit 2: API Service | |
| US-3.7 Original + converted amounts | Unit 2 (display) + Unit 3 (computes conversion) | Unit 3's Currency Conversion component computes; Unit 2 serves the stored result |
| US-4.1 Category trends dashboard | Unit 2: API Service | |
| US-4.2 Cash flow dashboard | Unit 2: API Service | |
| US-4.3 Bank breakdown dashboard | Unit 2: API Service | |
| US-4.4 Dashboard date/currency filters | Unit 2: API Service | |
| US-4.5 Drill down to transactions | Unit 2: API Service | |
| US-4.6 Approximate-conversion disclosure | Unit 2 (display) + Unit 3 (computes/flags) | |
| US-5.1 Login | Unit 2: API Service | |
| US-5.2 Edit category whitelist | Unit 2: API Service | |
| US-5.3 Configure external service credentials | Unit 2 + Unit 3 (each unit reads its own required secrets from its own environment) | No runtime component owns this; it's environment/deployment configuration |

## Coverage Validation (Step 8)

- **All 24 stories assigned**: Yes — every story above has at least one primary unit.
- **Unassigned units**: None — Unit 1 (Database) has no directly-assigned stories since it's a foundational schema unit with no user-facing behavior of its own; it is exercised indirectly by every story that reads/writes data (all of them except pure-config stories like US-5.3).
- **Cross-cutting stories flagged**: US-1.2, US-3.4, US-3.7, US-4.6, US-5.3 explicitly span 2 units — this is expected given the async, decoupled architecture (Application Design `services.md`) and is not a design flaw; each spanning story has a clear split of responsibility documented above.
