# Application Design Plan — Nightly Transaction Backup

**Role**: Software architect, identifying components/methods/services/dependencies for Epic 7.

## Design decisions made and explained (not asked) — with reasoning

Each is a technical call with a single defensible answer given this project's own established conventions, not a product-owner tradeoff:

| Category | Decision | Why this isn't a question |
|---|---|---|
| **Component identification** | New **Backup Manager Component** in Ingestion Worker Service. | Backup is time-triggered (a schedule check), not queue-triggered like the existing Ingestion Orchestrator (which only ever picks up a *queued* run/job row), and produces a different artifact (a CSV snapshot, not persisted `Transaction` rows from a statement). Distinct enough from the Orchestrator's stated purpose to warrant its own component — same granularity precedent as the Recategorization Review Component (Epic 6), which also got its own component rather than being squeezed into an existing one. |
| **Component identification** | Extend the existing **Drive Connector Component** (Ingestion Worker) with upload/create-folder/list/delete methods, rather than a new Drive-facing component. | `components.md` already states this component's purpose as "All interaction with Google Drive" — that's exactly what new backup-folder operations are. Matches how it already owns list/download; no reason to split Drive I/O across two components. |
| **Component identification** | New **Backup Status Component** in API Service, separate from the existing Ingestion Trigger & Status Component. | Ingestion Trigger & Status Component's stated purpose is specifically "the API Service's side of the async ingestion workflow" (the run/job queue) — backups aren't part of that queue and read a different table. Matches the Recategorization Review Component precedent: a distinct, mostly-read reporting capability over its own table gets its own component. |
| **Component identification** | Frontend: extend the single **Frontend SPA** component's responsibilities (existing convention treats the whole SPA as one component, not one-component-per-page/panel). | Every other page and the Epic 6 Review-page addition already follow this convention in `components.md` — the new Backup Status panel is one more responsibility on the same component, not a new one. |
| **Service layer / orchestration** | Backup Manager is checked **at most once per poll cycle**, and only when neither a queued run nor a queued job was found that cycle — a third branch alongside the existing run/job checks in `poll_once()`. | Preserves NFR-1 (the existing "one run/job at a time" invariant, WR-8) by extending its existing "at most one of {run, job} per cycle" pattern to "at most one of {run, job, backup}" rather than introducing separate concurrency handling. |
| **Component dependencies** | Backup Status Component (API Service) depends only on the shared database (`backup_runs` table) — never calls the Ingestion Worker Service directly. | Required to hold the project's one hard architectural rule (API Service and Ingestion Worker Service coordinate only through shared DB rows, never direct calls) — same rule the Recategorization Review Component already follows. |
| **Design patterns / interface style** | Plain REST resource endpoint(s) under a new router (e.g. `/backups`), matching existing router conventions (`/transactions`, `/dashboards`, `/categories`, `/ingestion`, recategorization's router). | One consistent API style already exists project-wide; no reason to deviate for one feature. |

No component/service/dependency-design question in this stage has a genuine open tradeoff beyond what's above — Requirements (both clarification rounds) and Stories already resolved every product-facing decision (destination folder, retention count, catch-up behavior, no-retry rule, panel placement and dual failure-mode display). This plan is presented for approval, not for `[Answer]:` input.

## Execution Checklist

- [ ] Update `components.md` (addendum style, matching the existing "Addendum (date, during stage X)" pattern):
  - [ ] New: Backup Manager Component (Ingestion Worker Service)
  - [ ] Addendum: Drive Connector Component (Ingestion Worker) — upload/create-folder/list/delete
  - [ ] New: Backup Status Component (API Service)
  - [ ] Addendum: Frontend SPA — Backup Status panel on the Review page
  - [ ] Addendum: Shared Data Store — new `backup_runs` tracking table
- [ ] Create `component-methods.md` entries (signatures only, no business rules — those come in Functional Design):
  - [ ] Drive Connector: `ensureBackupFolderExists`, `uploadFile`, `listBackupFolderFiles`, `deleteFile`
  - [ ] Backup Manager: `isBackupDueNow`, `runBackup`, `enforceRetention`
  - [ ] Backup Status Component: `getLatestBackupStatus`
- [ ] Update `services.md` — orchestration note: `poll_once()` gains a third, lowest-priority branch for the Backup Manager, evaluated only when no run/job was picked up this cycle
- [ ] Update `component-dependency.md` — add Backup Manager (→ Drive Connector, same service; → Shared DB), Drive Connector's unchanged external dependency (Google Drive API, now including write scopes), Backup Status Component (→ Shared DB only)
- [ ] Regenerate `application-design.md` (consolidated doc) to include all of the above
- [ ] Update `aidlc-state.md`
