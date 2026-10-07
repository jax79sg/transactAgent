# Code Generation Plan — Versioned Releases and Guide (issue #27, 2026-10-07)

**Requirements**: `inception/requirements/versioned-guide-requirements.md`. **Units**: Database (shared reader), API Service, Ingestion Worker (log line), Frontend, deployment files, a new `scripts/` tool, the guide itself. **Branch**: `feature/issue-27-versioned-guide`.

## Steps
1. [x] **One number** — `VERSION` = 1.0.0; `transactagent_db/version.py` (`app_version()`, never raises, "unknown" when missing or malformed); the Dockerfiles copy the file (API and worker to `/app/VERSION`, the frontend build next to its config).
2. [x] **API and worker** — `GET /version` (unauthenticated); the worker's startup log names its release.
3. [x] **Frontend** — the number baked in at build time (`vite.config.ts` through a pure `parseVersion`), shown on the sign-in screen and in the top bar (linking to `/settings#about`); the Settings About card (interface and server release, drift warning, guide and releases links, scroll-to-hash); `lib/guideLinks.ts`; `api/version.ts`.
4. [x] **Guide tool** — `scripts/guide.py` (`check`, `snapshot`), `docs/releases.json` and `docs/releases.html`, the **Guide** workflow, `RELEASING.md`.
5. [x] **Guide content** — demo data ingested through the real worker pipeline (with a genuine duplicate pair), 14 screenshots captured with headless Chrome at the guide's existing size, `docs/index.html` revised and stamped, `docs/v1.0.0/` cut.
6. [x] **Tests** — database 18 (version reader), API 4 (`/version`), frontend 37 new (parse, links, API, nav, login, About card), tool 35.
7. [x] **Verification** — suites and linters; 42 mutation checks (24 Python, 18 frontend) all caught after two tests were added for survivors; the three images built and shown to carry the number; the guide rendered in Chrome (no console errors, no broken images, archive and index pages checked).
8. [x] **Documentation and progress** — requirements, this plan, summary, `aidlc-state.md`, `audit.md`, README.

## Completion criteria
All steps `[x]`; `python scripts/guide.py check` passes; the guide matches `VERSION`. **Met.**
