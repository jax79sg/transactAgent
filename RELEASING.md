# Releasing

The app has one release number, **`VERSION`** at the repository root, written `MAJOR.MINOR.PATCH`. Everything that
shows or uses it reads that file: the API (`GET /version`), the worker's startup log, the frontend build (shown on the
sign-in screen, in the top bar and under **Settings → About this release**), and the user guide.

Every release keeps its own copy of the user guide, published with the latest one on GitHub Pages
(`https://jax79sg.github.io/transactAgent/`): the latest guide at the root, release `X.Y.Z` at `/vX.Y.Z/`, and an index
of all of them at `/releases.html`. The **Guide** workflow fails a pull request in which `VERSION`, the latest guide,
the archived copies and the index disagree, so the guide cannot silently fall behind a version bump.

## Cutting a release

1. **Update `docs/index.html` for what changed** (text and screenshots), and set its stamp to the new number: the
   `<meta name="guide-version" content="…">` near the top and the "What's new" list in the *Releases* section.
2. **Bump `VERSION`** (`MAJOR` for a change that needs action on upgrade, `MINOR` for a feature, `PATCH` for a fix).
3. **Snapshot the guide**:

   ```bash
   python scripts/guide.py snapshot --summary "One line on what this release adds"
   ```

   This writes `docs/vX.Y.Z/index.html`, records the release in `docs/releases.json` and rewrites
   `docs/releases.html`. Commit all of it.
4. **Check** with `python scripts/guide.py check` (CI runs the same), open a pull request, and after it merges tag the
   merge commit `vX.Y.Z`.
5. **Rebuild and restart every service** (`docker compose up -d --build`) so the interface and the server report the
   same release — Settings shows a warning when they differ.

Archived guides are never edited afterwards: they are what that release shipped with. Each one is about 1.5 MB (the
screenshots are embedded), which is the cost of a self-contained page.
