# Application Design Plan — Background Process Visibility

## Scope
One new API Service component (**Background Activity Component**), read-only against the existing `ingestion_runs`/`recategorization_jobs` tables — the same tables `is_ingestion_worker_busy()` already reads for restart guidance, but with a broader response (job-type identification + recent history) that endpoint doesn't provide. One addendum to the Frontend SPA component (nav bar indicator + detail panel). No changes to Database or Ingestion Worker Service.

## Design Checklist
- [x] Generate `components.md` addendum — new Background Activity Component (API Service), Frontend SPA addendum
- [x] Generate `component-methods.md` addendum — method signature(s) for the new component
- [x] Generate `services.md` addendum — orchestration note (read-only, no new orchestration point of note)
- [x] Generate `component-dependency.md` addendum — dependency row + data flow note
- [x] Update `application-design.md` consolidated doc

## Open Questions
None. Requirements (`background-process-visibility-requirements.md`) and stories (`background-process-visibility-stories.md`) already fully determine component boundaries: this is a read-only extension pattern this project has used four times before (Backup Status Component, Recurring Payments Component's status summary, `is_ingestion_worker_busy`'s restart guidance, Recategorization Review's pending count) — same "one hard architectural rule" (API Service never calls the Ingestion Worker Service directly, only reads the Shared DB) applies unchanged. Proceeding directly to generation per the user's standing blanket approval for this feature.
