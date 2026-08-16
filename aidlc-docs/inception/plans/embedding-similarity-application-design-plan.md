# Application Design Plan — Local Embedding-Based Semantic Similarity

**Role**: Software architect, converting `embedding-similarity-requirements.md` + `embedding-similarity-stories.md` into component-level design.

## Genuinely open item

None requiring a new user question — the 10-question requirements round plus 2 clarification rounds already
resolved every product-level decision. What follows are architecture/design decisions at the appropriate
altitude for this stage (component boundaries, method signatures, dependencies — not detailed business
rules, which stay deferred to Functional Design). Each is documented, not asked, consistent with this
project's established practice, and flagged here for correction at the review gate if any reads wrong.

## Key Design Resolution: two embedding computations, not one

FR-3/FR-4 require embedding-based candidate search to run at match time (categorize, recategorize, recurring
match, detection). FR-6 requires the *persisted* embedding (the one the badge reflects) to be computed
**asynchronously/batched**, decoupled from the ingestion run. These aren't in tension once split into two
distinct operations:

1. **Query-time (synchronous, transient, not persisted)**: whenever the Categorization Engine, Recurring
   Payment Manager, or Detection Scan needs to search for a candidate, it computes a one-off embedding of
   the description being matched *right now* and queries the Vector Store Client for nearest neighbors among
   *already-stored* embeddings. This is required for FR-3/FR-4 to mean anything at match time, and it soft-
   fails per FR-10 (oMLX unreachable -> fall through to the fuzzy-text matcher) exactly like every other step
   here.
2. **Storage-time (asynchronous, batched, per FR-6)**: a transaction's *own* embedding — the one that makes
   it a future candidate for other transactions, and the one FR-7's badge reflects — is computed and
   persisted by a new background poll cycle, not blocking ingestion.

Consequence worth flagging explicitly: a brand-new transaction's *own* first categorization attempt (during
the ingestion run that creates it) cannot benefit from embedding-based matching *against candidates that
haven't been embedded yet either* — but it can immediately search against every *already-embedded* historical
candidate via (1) above. Only its own persisted embedding (making *it* a future candidate) waits for the
async job. This is the natural, minimal-surprise reading of FR-3/FR-4/FR-6 together, not a new product
decision — flagged here for correction if this reading is wrong.

## Design Decisions

1. **Two new Ingestion Worker Service components**, following this project's existing patterns:
   - **Vector Store Client Component** — "all interaction with the vector database," mirroring Drive
     Connector's "all interaction with Google Drive" role. Shared read/write interface, called by every
     component that needs to store or query embeddings.
   - **Embedding Manager Component** — owns *when* embeddings get computed and persisted: the async/batched
     poll-cycle job (FR-6) and the one-time historical backfill (FR-11), mirroring Backup Manager's
     "owns a time-triggered concern" role. Does not itself decide matching outcomes — that stays with the
     Categorization Engine / Recurring Payment Manager, same separation of concerns as today.
2. **Backfill and forward embedding share one mechanism**, not two: every transaction (new or pre-existing)
   gets an `embedding_status` field (Database addendum), defaulting to a pending state. A single poll-cycle
   branch processes a bounded batch of pending transactions each cycle — this is simultaneously "the async
   embedding job" (FR-6) for new transactions and "the one-time backfill" (FR-11) for historical ones,
   naturally idempotent/resumable (NFR-4) since it just keeps consuming the pending backlog.
3. **The vector store needs two logical collections**, not one: transaction-description embeddings (used by
   Categorization Engine, Detection Scan) and recurring-payment-name embeddings (used by Recurring Payment
   Manager, matching WR-16's existing target — a payment's `name`, not another transaction). The Vector
   Store Client's methods take a collection/kind parameter accordingly.
4. **API Service**: no new component — `embedding_status` is added to the existing Transaction Management
   Component's DTOs (`listTransactions`/`getTransaction`), following the same "extend the existing DTO"
   pattern already used for e.g. conversion-approximate flags. A dedicated new component would be
   unjustified — this is a single read-only field on an existing entity, not a new capability surface.
5. **Frontend SPA**: no new component — the badge is rendered inline in the existing transaction list,
   following this project's established "one Frontend SPA component" convention (same as every prior badge/
   panel addition).
6. **oMLX stays fully outside the application design's dependency graph as a "black box" external API** —
   like the existing LLM/FX/Drive external dependencies, just user-managed rather than cloud-hosted. No
   component owns "managing oMLX's lifecycle"; the Embedding Manager and Vector Store Client only *call* it.

## Execution Checklist

- [x] Update `components.md`: add Vector Store Client + Embedding Manager (Ingestion Worker Service);
  addenda to Categorization Engine, Recurring Payment Manager, Transaction Management Component (API
  Service), Frontend SPA, Shared Data Store (new field + new Vector Store subsection)
- [x] Update `component-methods.md`: method signatures for the two new components; addenda to
  `categorize()`/`recategorizeUnsureFromPrecedent()`, `matchNewTransaction()`/`runDetectionScan()`,
  `listTransactions()`/`getTransaction()`
- [x] Update `services.md`: new `poll_once()` branch (fifth); note on the two-computation split from above
- [x] Update `component-dependency.md`: new dependency-matrix rows; new external dependency (oMLX) and new
  Vector DB datastore; regenerate + width-verify the ASCII diagram
- [x] Update `application-design.md`: consolidated summary addendum + story-traceability table for Epic 9
- [x] Update `aidlc-state.md`

## Mandatory Artifacts
- [x] `components.md`, `component-methods.md`, `services.md`, `component-dependency.md`,
  `application-design.md` — all updated in place with dated addenda (this project's established pattern for
  post-completion changes, preserving prior history untouched)
