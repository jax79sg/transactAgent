# Application Design Plan — Recurring Payments, Budget Alerts & Subscription Detection

**Role**: Software architect, identifying components/methods/services/dependencies for Epic 8.

## Design decisions made and explained (not asked) — with reasoning

| Category | Decision | Why this isn't a question |
|---|---|---|
| **Component identification** | New **Recurring Payment Manager Component** in Ingestion Worker Service. | Matching/trust/detection is a distinct capability from the existing Ingestion Orchestrator (queue-triggered, statement-shaped) and Categorization Engine (assigns one category to one new transaction). Same granularity precedent as Backup Manager (Epic 7) — a new, distinct capability gets its own component. |
| **Component identification/reuse** | Reuses the existing Categorization Engine's similarity matcher (the same `find_best_match`-style function already used for categorization and recategorization) rather than building a second matcher. | NFR-1 requires this explicitly. The matcher is already description/amount-aware and configurable per call site (see `categorization/similarity.py`) — recurring-payment matching is one more call site, not a new algorithm. |
| **Component identification** | New **Recurring Payments Component** in API Service, separate from Dashboard/Insights and Recategorization Review. | It owns a distinct resource (the register + matches + detection suggestions) with its own CRUD/review surface — matches the precedent of Recategorization Review getting its own component rather than being folded into Transaction Management. |
| **Component identification** | Frontend: extend the single **Frontend SPA** component (existing convention). | Every prior feature followed this; the Dashboard's new section is one more responsibility on the same component. |
| **Service layer / orchestration** | Matching runs as part of the existing Ingestion Orchestrator's per-transaction persistence step (right after a transaction is categorized and saved) — not a separate poll-loop branch like Backup Manager. Detection (FR-12) runs as a periodic scan, checked on the same lowest-priority poll-loop branch pattern Backup Manager established, extended to a fourth check. | Matching needs to happen exactly when a *new* transaction appears — the natural hook is the same pipeline step that already persists it (`orchestrator/pipeline.py::_persist_transaction`), avoiding a second pass over the same data. Detection, by contrast, is not transaction-triggered — it's a periodic "look for patterns across history" job, which is exactly what Backup Manager's poll-loop branch pattern already solves; reusing that pattern (checked only when nothing else is due that cycle) needs no new concurrency handling. |
| **Component dependencies** | Recurring Payments Component (API Service) depends only on the shared database — never calls the Ingestion Worker Service directly. | Holds the project's one hard architectural rule, same as every prior review-style component (Recategorization Review, Backup Status). |
| **Design patterns / interface style** | Plain REST resource endpoints under a new `/recurring-payments` router, matching existing router conventions. | One consistent API style already exists project-wide. |
| **Frontend badge placement** | The attention-needed badge (US-8.7) decorates the **Dashboard** nav link (since that's where this feature lives, FR-4), the same way `PendingReviewBadge` decorates the Review link. | Direct visual precedent already established in `NavBar.tsx`; the badge belongs next to where its content lives. |

No component/service/dependency-design question in this stage has a genuine open tradeoff beyond what's above — Requirements and Stories already resolved every product-facing decision. This plan is presented for approval, not for `[Answer]:` input.

## Execution Checklist

- [ ] Update `components.md`:
  - [ ] New: Recurring Payment Manager Component (Ingestion Worker Service)
  - [ ] Addendum: Categorization Engine Component — its similarity matcher is now also called by Recurring Payment Manager (no logic change, new caller)
  - [ ] New: Recurring Payments Component (API Service)
  - [ ] Addendum: Frontend SPA — Dashboard Recurring Payments section + Dashboard-nav-link badge
  - [ ] Addendum: Shared Data Store — new recurring-payment register, match, and detection-suggestion tables
- [ ] Create `component-methods.md` entries (signatures only):
  - [ ] Recurring Payment Manager: `matchNewTransaction`, `runDetectionScan`
  - [ ] Recurring Payments Component: register CRUD, bulk import, list/approve/reject matches, list/dismiss/add-from detection suggestions, status summary
- [ ] Update `services.md` — orchestration note: matching hooks into the existing per-transaction persistence step; detection becomes poll_once()'s fourth branch
- [ ] Update `component-dependency.md` — new dependency-matrix rows; ASCII diagram updated + width-reverified
- [ ] Regenerate `application-design.md` (consolidated doc + story-traceability table)
- [ ] Update `aidlc-state.md`
