# Build and Test Summary — Background Process Visibility

Only 2 of the 4 units are affected (API Service, Frontend SPA) — Database and Ingestion Worker Service needed zero changes, since the two in-scope job types already write everything this feature reads. No migration. Both changed units rebuilt and redeployed against the real running project (`docker compose build` + `up -d api-service frontend`) against the real live stack.

## API Service

- New `background_activity/` package: `schemas.py`, `repository.py` (AR-35/36/37), `service.py`, `router.py` — `GET /background-activity/summary`, registered in `main.py`.
- 14 new tests (12 repository-level, 4 endpoint-level — some overlap in naming across the two files by design, covering both layers): idle state, running-ingestion-run, running-recategorization-job, defensive tie-break when both tables somehow report `running` simultaneously (AR-35), combine-across-both-tables sort correctness, `limit` respected, running row correctly excluded from its own history by construction (AR-37).
- Fixed 3 real test-fixture gaps found via actual execution, not assumption: `Transaction` requires `bank_name`/`category_id`/`category_source` NOT NULL — none obvious from this feature's own scope, only discovered by running the tests and reading the resulting `IntegrityError`s.
- `ruff check` clean (after auto-fixing import ordering). Full API Service suite: **253/253 passing** (up from 239).
- `docker compose build api-service` verified clean. Redeployed (`docker compose up -d api-service`), container healthy.

## Frontend SPA

- Real design gap found and fixed during Code Generation (documented as a Functional Design correction, not silently patched): the original `frontend-components.md` wording said the idle-state indicator "renders nothing," but that would remove the only way to reach the recent-history panel (US-11.3) when nothing is currently running. Corrected: `ActivityIndicator` always renders as a small clickable dot; only its visual weight changes (muted/static when idle, pulsing + labeled when a job is running) — matches FR-BPV-4's actual wording ("hidden/**unobtrusive**", not "hidden entirely").
- New `api/backgroundActivity.ts`, `types.ts` +4 DTOs, `NavBar.tsx` +`ActivityIndicator` (3s poll matching the Ingestion page's own cadence per NFR-BPV-1, click-to-open popover panel, one shared `useQuery` backs both the always-visible dot and the on-demand panel content).
- `NavBar.test.tsx` +4 new tests (idle muted state with no label, running state shows the specific job type not a generic label, panel opens on click even while idle, empty-history message) — plus default `getActivitySummary` mocks added to the two pre-existing describe blocks so they're unaffected by the new always-on query.
- `eslint`, `tsc -b`, `vite build` all clean (ran inside a `node:20-alpine` container, no local Node install on this machine). Full Frontend suite: **99/99 passing** (up from 95).
- `docker compose build frontend` verified clean. Redeployed (`docker compose up -d frontend`), container healthy.

## Live verification

- Minted a real JWT via the app's own `issue_token` against a real user row (never touched a plaintext password).
- `GET /background-activity/summary` confirmed live against the real database — and caught a genuinely live, real-time example while doing so: a real `recategorization_job` row was actually `running` at the moment of the check (the Ingestion Worker was mid-scan), with `recent` correctly populated by 10 real prior completions, most recent first.
- Confirmed the deployed frontend bundle contains the new markup/endpoint string (`activity-indicator`, `background-activity/summary`) via `grep` against the container's own served output.
- Browser-based visual verification performed (this session had browser automation available): logged in via a JWT injected directly into `sessionStorage` (never a login form/plaintext password), confirmed the nav bar shows a green pulsing dot labeled "Recategorization scan in progress" — visually distinct from the two existing amber count-pill badges — and that clicking it opens the panel showing the current job plus the real recent-completions history, matching the live API response exactly. Test session's token cleared from `sessionStorage` afterward.

## Final state

All 5 containers (`transactagent-db`, `transactagent-vector-db`, `transactagent-worker`, `transactagent-api`, `transactagent-frontend`) healthy after redeploy — `transactagent-worker` was already in a pre-existing `unhealthy` Docker healthcheck state before this change (confirmed via its logs it was actively processing embedding batches successfully throughout; unrelated to this feature, not investigated further as out of scope). No migrations, no schema changes, real user data untouched.

**Full unit test total for this feature**: 14 new API Service tests (253/253 total) + 4 new Frontend tests (99/99 total) = 18 new tests, zero regressions across both affected units.
