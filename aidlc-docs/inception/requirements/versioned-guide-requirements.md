# Requirements — Versioned Releases and an Up-to-Date, Archived Guide (GitHub issue #27, 2026-10-07)

**Request (issue #27, jax79sg):** "The guide is not updated with the latest version of the software. Suggest you somewhat keep a version of the release, and a reachable archive of guides for different releases. That said, the release needs to be clear on the app as well."
**Depth:** Standard. **Branch:** `feature/issue-27-versioned-guide`.

## Findings
- The guide is one self-contained page (`docs/index.html`, nine embedded screenshots) published on GitHub Pages and linked from the README. It was last refreshed on 2026-08-17 and so lacks everything shipped since: dark mode, sortable tables, the reworked recurring payments, the top-bar activity indicator, probable duplicate statements, the Gemini options, and the phone fixes. Nothing recorded which release it described, and the app had no release number at all (the packages say 0.1.0 and nothing reads it).
- The reason the guide fell behind is structural, not a one-off: nothing ties a guide to a release or fails when they drift.

## Requirements
- **GV-1** One release number, `VERSION` at the repository root (`MAJOR.MINOR.PATCH`), read by everything that shows or uses it.
- **GV-2** The release is clear in the app: the sign-in screen, the top bar of every page, and a Settings "About this release" card that also shows the server's release (new unauthenticated `GET /version`), warns when the interface and the server differ, and links to the guide for that release and to the list of all releases. The worker logs its release at startup.
- **GV-3** Every release keeps its own copy of the guide, reachable from a published index: the latest at the root of the guide site, release X.Y.Z at `/vX.Y.Z/`, all listed at `/releases.html`. Each guide says which version it is for; an archived one says so prominently and links to the latest.
- **GV-4** A tool cuts a release's guide (`python scripts/guide.py snapshot`) and a check (`… check`, run by CI on every pull request) fails when `VERSION`, the latest guide's stamp, the archived copies, the index data and the index page disagree, so a version bump cannot ship without its guide.
- **GV-5** The guide is brought up to date for this release: new "top bar" and "Releases" sections; the Dashboard, Transactions, Ingestion, Review and Settings sections revised; retaken screenshots (fictional demo data, as before) of every changed screen, including the new probable-duplicate panel and comparison page, dark mode and the About card.
- **GV-6** The process is written down (`RELEASING.md`).

## Out of scope (stated, not forgotten)
- The Costs page (issue #28, its own pull request): the guide documents what is on `main`; when that merges, cutting 1.1.0 per RELEASING.md adds it, and the 1.0.0 archive stays as shipped.
- The Ask AI screenshot (that screen did not change and needs a live Gemini key to photograph) is kept.
- Forcing a guide edit for every feature (impossible to detect mechanically); the check only forces consistency with the version, and RELEASING.md puts the guide update ahead of the bump.

## Assumptions made without asking (revisit in review)
1. **The first number is `1.0.0`** and means "everything on main at the time of this change". Another number is a one-line change in `VERSION` (and a re-run of the snapshot).
2. The guide site stays on GitHub Pages at `https://jax79sg.github.io/transactAgent/`, as the README already says (the tool and the links assume `docs/` is what is published).
3. Each archived guide is a full copy (about 1.5 MB, screenshots embedded) rather than a shared set of images, so an old guide can never break when the latest one changes.
