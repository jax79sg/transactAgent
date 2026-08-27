---
name: git-issue-workflow
description: Git branching and PR workflow for implementing a feature or fix in this repo, especially one that originates from a GitHub issue. Use this whenever asked to process, pick up, implement, or fix a GitHub issue, and before the first commit of any feature-sized change (not a one-line tweak) — even if the request doesn't explicitly mention branches, PRs, or git. Also consult it before merging a PR or pushing to main, since it defines when those are (and aren't) appropriate.
---

# Git Issue Workflow

## Why this exists

On a direct-commit-to-main workflow, a feature's changes become indistinguishable from
every other commit on main the moment they land. There's no unit of review, no point
where the change can be looked at as a whole before it's permanent, and no clean way to
revert or keep iterating on just that change without touching unrelated history. A
branch plus a PR gives a feature a name, a diff, and a checkpoint before it becomes part
of the project's permanent history — that checkpoint is the entire point, so don't skip
past it just because the code itself is ready.

## When this applies

- The user asks you to pick up, process, or implement a GitHub issue.
- You're building any feature or fix substantial enough to span multiple files or
  commits — roughly, anything past a single-line tweak.
- Skip branching only for genuinely trivial changes (a typo fix, a config value, a doc
  update) where the user explicitly says to just commit/push it directly. When in doubt,
  branch — it costs almost nothing and is easy to fast-forward-merge if it turns out to
  be overkill.

## The workflow

1. **Branch before touching code.** Before the first edit, create a descriptively named
   branch off the default branch: `feature/<slug>` for a new capability, or
   `<issue-number>-<short-slug>` when a specific issue is driving it (e.g.
   `12-dark-mode` for issue #12). Branch first, not retroactively — branching after the
   fact means untangling which changes belong to the feature from whatever else landed
   on main in the meantime, which is exactly the mess branching exists to avoid.

2. **Commit at a reasonable grain as work progresses.** Commit when a logical unit of
   work is done (e.g. "requirements + stories", "backend endpoint + tests", "frontend
   wiring") rather than one mega-commit at the very end or a commit per file edit. The
   history should read as the story of how the feature came together — useful to
   whoever reviews it later, including future-you.

3. **Never push directly to the default branch for feature work.** Push the feature
   branch to `origin` instead:
   ```bash
   git push -u origin <branch-name>
   ```
   The default branch only receives commits via a merged PR, or an explicit, separate
   request from the user to push directly (see the trivial-change exception above).

4. **Open a PR — don't jump straight to merge.** Use `gh pr create` with a title, a
   summary, and a test plan, following this repo's usual PR conventions. If the work
   closes a GitHub issue, include a closing keyword in the PR body (`Closes #<n>`) so
   the issue closes automatically on merge instead of needing a separate step:
   ```bash
   gh pr create --title "..." --body "$(cat <<'EOF'
   ## Summary
   - ...

   Closes #<n>

   ## Test plan
   - [ ] ...
   EOF
   )"
   ```

5. **Functional approval is not merge approval.** The user saying a feature works
   correctly — "looks good," approving a build-and-test summary, confirming behavior in
   a live check — is not the same as approving the merge. Those are two different
   questions: "does this do what I wanted" and "is this ready to become part of main."
   Open the PR and hand it to the user rather than merging it yourself.

6. **Only merge, or push to main directly, when explicitly asked for that specific
   action, in those words.** "Commit this" doesn't mean "push to main." "Looks good"
   doesn't mean "merge." If a request is genuinely ambiguous about which of these is
   meant, ask rather than assuming the most permissive reading — merging and pushing to
   main are both hard to cleanly undo once other work lands on top.

7. **Clean up after merge.** Once a PR is merged, delete the now-merged feature branch
   both locally and on `origin`, if the user confirms or it's clearly stale and fully
   merged:
   ```bash
   git branch -d <branch-name> && git push origin --delete <branch-name>
   ```

## Quick reference

```bash
git checkout -b feature/<slug>              # or <issue-number>-<slug> — before any edits
# ... work, committing at logical checkpoints ...
git push -u origin feature/<slug>
gh pr create --title "..." --body "...Closes #<n>..."
# wait for explicit user go-ahead, THEN:
gh pr merge <number> --merge                # or --squash, matching this repo's convention
git branch -d feature/<slug> && git push origin --delete feature/<slug>
```

## Note for this repo specifically

This repo's `aidlc-docs/aidlc-state.md` already has a convention of naming the working
branch in a feature's tracking section (e.g. "Working on git branch
`feature/recurring-payments-budget-alerts`"). Keep doing that — it's the same
information this skill cares about, just recorded where the rest of the feature's
history already lives.
