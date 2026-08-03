# Application Design Plan — Recategorization Review Panel

**Role**: Software architect, identifying components/methods/services/dependencies for Epic 6.

## Design decisions made and explained (not asked) — with reasoning

Each is a technical call with a single defensible answer given this project's own established conventions, not a product-owner tradeoff:

| Category | Decision | Why this isn't a question |
|---|---|---|
| **Component identification** | New **Recategorization Review Component** in API Service, separate from the existing Transaction Management Component. | Matches this project's existing granularity — Ingestion Trigger & Status is already split out from Transaction Management despite being related; review/approval is an equally distinct capability (its own page, its own bulk-action semantics) from single-row category correction. |
| **Component identification** | Extend the existing **Categorization Engine Component** (Ingestion Worker) rather than create a new worker component. | The broadened search + two-tier split is a change to *how* the existing retroactive re-scan (FR-5.4) works, not a new capability — it already owns "the retroactive re-scan of existing UNSURE transactions triggered by a manual correction," per `components.md`. |
| **Component identification** | Frontend: extend the single **Frontend SPA** component's responsibilities (existing convention treats the whole SPA as one component, not one-component-per-page). | `components.md` already lists every other page (dashboards, transactions, ingestion) as responsibilities of one Frontend SPA component, not separate components — the Review page follows the same convention. |
| **Service layer / orchestration** | Approve/reject actions are **synchronous** direct DB writes from the new API Service component — no async job queue involved. | Directly analogous to the existing `PUT /transactions/{id}/category` endpoint (a single-row write, no LLM/external call). Proposal *generation* stays on the existing async path (ingestion-worker via `recategorization_jobs`, per NFR-RR-1) — only the human's approve/reject action is synchronous, matching the existing sync-for-user-actions / async-for-background-work split already established by this project (e.g., Ask AI is sync, ingestion is async). |
| **Component dependencies** | The new API Service component depends only on the database (reads/writes proposal rows) — it never calls Ingestion Worker directly. | Required by NFR-RR-1 and consistent with the project's one hard architectural rule (`api-service` and `ingestion-worker` coordinate only through shared rows). |
| **Design patterns / interface style** | Plain REST resource endpoints under a new router, matching existing router conventions (`/transactions`, `/dashboards`, `/categories`, `/ingestion`). | Project has one consistent API style already; no reason to introduce a different pattern for one feature. |

No component/service/dependency-design question in this stage has a genuine open tradeoff beyond what's above — Requirements and Stories already resolved the product-facing decisions (scope, timing, bulk actions, naming). This plan is presented for approval, not for `[Answer]:` input.

## Execution Checklist

- [ ] Update `components.md` (addendum style, matching the existing "Addendum (date, during stage X)" pattern already used for Ingestion Trigger & Status):
  - [ ] New: Recategorization Review Component (API Service)
  - [ ] Addendum: Categorization Engine Component (Ingestion Worker) — broadened search + two-tier split
  - [ ] Addendum: Frontend SPA — Review page + nav badge responsibility
  - [ ] Addendum: Shared Data Store — new proposal-record table
- [ ] Create `component-methods.md` entries (signatures only, no business rules — those come in Functional Design):
  - [ ] Categorization Engine: broadened candidate search method, auto-apply method
  - [ ] Recategorization Review Component: list pending, approve (single + bulk), reject (single + bulk)
- [ ] Update `services.md` — orchestration note: proposal generation stays on the existing async job path; approve/reject is a new synchronous path in API Service
- [ ] Update `component-dependency.md` — add the new component's dependency edge (API Service → Database only) and confirm no new edge to Ingestion Worker
- [ ] Regenerate `application-design.md` (consolidated doc) to include all of the above
- [ ] Update `aidlc-state.md`
