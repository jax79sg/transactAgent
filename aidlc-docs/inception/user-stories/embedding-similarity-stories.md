# User Stories — Local Embedding-Based Semantic Similarity

Appends **Epic 9** to the project's existing story set (`stories.md` Epics 1–5, `recategorization-review-stories.md` Epic 6, `nightly-backup-stories.md` Epic 7, `recurring-payments-stories.md` Epic 8), kept separate so prior history stays untouched.

**Persona**: **The Account Owner** (`personas.md`) — unchanged; this feature introduces no new persona.
**Granularity/format**: Coarse, epic-level, Given/When/Then + edge cases — matches the existing convention.
**Traceability**: Each story references `embedding-similarity-requirements.md`'s FR/NFR IDs.
**Naming note**: examples in acceptance criteria below use invented placeholder payees — never the Account Owner's real, real-world list.

---

## Epic 9: Local Embedding-Based Semantic Similarity

### US-9.1: See which transactions have a computed embedding
**As** the Account Owner, **I want** to see a badge on transactions whose embedding has been computed **so that** I can tell which transactions have been fully processed by the background embedding job and which are still catching up.

**Traces to**: FR-6, FR-7

**Acceptance Criteria**:
- *Happy path*: Given a transaction whose embedding has finished computing, When I view the transaction list, Then it shows the embedding-computed badge.
- *Happy path — not yet computed*: Given a transaction just ingested moments ago, When I view the transaction list before the background job has reached it, Then no badge is shown — no error, no misleading state.
- *Edge case — badge meaning is narrow*: Given a transaction shows the badge, When I look at it, Then the badge tells me only that its embedding exists — it makes no claim about whether a similar past transaction was found, or about the transaction's category confidence.

### US-9.2: Get correctly matched to a past payment even when the wording differs
**As** the Account Owner, **I want** a repeat payment to the same payee to be recognized as similar even when its description varies more than a text-matching tool could handle **so that** I don't have to manually recategorize things that are obviously the same kind of payment.

**Traces to**: FR-1, FR-3, FR-4, FR-5

**Acceptance Criteria**:
- *Happy path*: Given a past transaction is already categorized (e.g. manually corrected to "Dining"), When a new transaction to the same payee is ingested with a semantically similar but not fuzzy-text-similar description, Then embedding-based similarity finds it as precedent and it's categorized the same way, following the same manual-source-precedence rule (WR-3) as today.
- *Happy path — falls back when embeddings don't help either*: Given no candidate clears the embedding-similarity threshold, When categorization runs, Then it falls back to the existing fuzzy-text matcher (WR-3/WR-20) exactly as it behaves today — nothing about the existing fallback path changes.
- *Edge case — applies beyond categorization too*: Given the same embedding-first-then-fuzzy-fallback behavior, When a transaction is matched against my recurring payments (Epic 8) or considered by the detection scan, Then the same matching order applies there too, not just during categorization/recategorization.

### US-9.3: Trust that the false-positive protection still holds
**As** the Account Owner, **I want** the existing protection against two similarly-worded but unrelated payments being confused with each other to keep working under the new matching method **so that** switching to embeddings doesn't quietly reintroduce a bug this app already fixed once (the AXS PTE LTD incident).

**Traces to**: FR-5, NFR-1

**Acceptance Criteria**:
- *Happy path — regression scenario*: Given two transactions to the same bill-payment-kiosk-style payee with near-identical descriptions but wildly different amounts (mirroring the real AXS PTE LTD incident this project already fixed once), When one is corrected and the other is considered as a candidate, Then the amount-range gate still excludes it as a match — regardless of how high its embedding-similarity score is.
- *Edge case — gate applies identically either way*: Given a candidate is found via embedding similarity instead of fuzzy-text similarity, When the amount-range gate is evaluated, Then it's applied exactly the same way it is for a fuzzy-text-sourced candidate — there is no separate, weaker check for the embedding path.

### US-9.4: Keep working normally when the local embedding service isn't running
**As** the Account Owner, **I want** statement ingestion and categorization to keep working even if my locally-run embedding service isn't up **so that** a piece of optional local infrastructure I manage myself never blocks my core workflow.

**Traces to**: FR-10

**Acceptance Criteria**:
- *Happy path — graceful degradation*: Given the local embedding endpoint is unreachable, When I ingest a new statement, Then extraction, categorization (via the fuzzy-text fallback), and everything else proceeds normally, with no failed run and no error surfaced to me.
- *Edge case — no badge, no side effect*: Given a transaction's embedding call failed, When I view it in the transaction list, Then it simply shows no badge (US-9.1) — the same appearance as one that just hasn't been processed yet, not a distinguishable "error" state.

### US-9.5: Benefit from smarter matching on my existing history too, not just new statements
**As** the Account Owner, **I want** my already-ingested transactions to also get embeddings, once, **so that** semantic matching has my full history to compare against right away, instead of slowly rebuilding usefulness one new statement at a time.

**Traces to**: FR-11

**Acceptance Criteria**:
- *Happy path*: Given transactions already in the system before this feature existed, When the one-time backfill runs, Then each of them eventually shows the embedding-computed badge (US-9.1), same as newly-ingested ones.
- *Edge case — safe to interrupt*: Given the backfill is interrupted partway (e.g. a restart), When it resumes, Then it picks up remaining transactions without recomputing ones already done or leaving duplicates.
- *Edge case — doesn't block normal use*: Given the backfill is still running, When I use the app for anything else (viewing transactions, ingesting a new statement, reviewing categories), Then nothing is blocked or slowed to the point of being noticeable.
