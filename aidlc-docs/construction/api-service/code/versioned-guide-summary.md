# Summary — Versioned Releases and Guide (GitHub issue #27, 2026-10-07)

**Request:** the guide was out of date; keep release versions and a reachable archive of guides; make the release clear in the app. **Requirements / plan:** `inception/requirements/versioned-guide-requirements.md`, `construction/plans/versioned-guide-code-generation-plan.md`. **Branch:** `feature/issue-27-versioned-guide`.

## What was built
- **A release number** (`VERSION` = **1.0.0**) that every part reads: `GET /version`, the worker's startup log, the frontend build, the guide check. Shown on the sign-in screen, in the top bar of every page (linking to Settings) and in **Settings → About this release**, which also reports the server's release, warns if it differs from the interface's, and links to that release's guide and to the list of all releases.
- **A guide per release.** `scripts/guide.py snapshot` stores `docs/vX.Y.Z/index.html` (stamped, with an "archived guide" banner), records the release in `docs/releases.json` and writes `docs/releases.html`; `scripts/guide.py check` (the new **Guide** workflow) fails a pull request when `VERSION`, the latest guide, the archives and the index disagree. `RELEASING.md` is the checklist.
- **The guide brought up to date for 1.0.0** (it described the app of 2026-08-17): new *The top bar* and *Releases* sections (with "What's new in 1.0.0"); revised Dashboard (the reworked recurring payments), Transactions (sorting), Ingestion (run files, skipped duplicates), Review (the probable-duplicate panel, comparison page, money in/out) and Settings (the Gemini choices, duplicate settings, About card) sections; **14 retaken screenshots** of fictional demo data (the Ask AI one is kept).

## How the screenshots were made
Fictional statements for three banks (May to October 2026) were ingested through the real worker pipeline with Drive and extraction mocked, so the runs, accounts and a genuine duplicate pair are exactly what the app produces; recurring payments, suggestions, disagreements, a proposal and a backup record were added; generic categories were used (not yours). Chrome (headless, your installed copy) walked the real built frontend at the guide's existing 1100×800 size.

## Verification
- Suites: database 206, ingestion worker 715, API 377, frontend 252, release tool 35 — all pass; `ruff`, `tsc` clean, `eslint` 0 errors.
- **42 mutation checks, all caught** (24 Python, 18 frontend); two survivors led to new tests (the build's reading of the version file; the server-version request).
- The API, worker and frontend images were built from this branch: both Python images read `1.0.0` from `/app/VERSION` and the frontend bundle contains it.
- The guide, its archive and the index rendered in Chrome: no console errors, no broken images.
- Not run: the nightly Playwright end-to-end suite (it needs the full docker-compose stack).

## Found while doing this (not fixed here; chips offered)
- The Dashboard's default date range uses the UTC date, so east of Greenwich "From" is a day early and "To" is yesterday until 08:00 (the screenshot of a Singapore browser showed 30/04/2026).
- An annual payment's "Set aside/mo" shows an unrounded 28-digit decimal.
- The Transactions page still has an unsortable Description column: issue #23, already with PR #24 (whose frontend check fails).

## Decisions left to the user
1. **The number 1.0.0** and what it means (assumption 1 in the requirements).
2. **Publishing:** GitHub Pages serves the guide only once this merges to `main`; the About card's links point at the published address and will 404 until then.
3. **The Costs page** (PR for #28) is not in this guide; after it merges, cut 1.1.0 per RELEASING.md.
