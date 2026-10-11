# Claude Code usage of this project

`SUMMARY.md` is the readable result and `ledger.json` the data behind it. Both are written by
`scripts/claude_usage.py`; read the caveats at the bottom of `SUMMARY.md` before quoting a figure.

## Refreshing it

```
python scripts/claude_usage.py report     # print, change nothing
python scripts/claude_usage.py update     # merge Claude Code's transcripts into ledger.json, rewrite SUMMARY.md
```

Commit the two files with the next pull request. `update` reads this project's transcripts and those of its
git-worktree sessions from `~/.claude/projects/`, and the ledger only ever grows, so a row survives the transcript it
came from being deleted. Sessions run on another machine are not seen.

## Keeping it up to date automatically

The ledger is meant to be refreshed whenever a Claude Code session ends. That is a hook in
`.claude/settings.local.json`, which git ignores, so it belongs to this machine only:

```json
"hooks": {
  "SessionEnd": [
    {
      "hooks": [
        {
          "type": "command",
          "command": "cd \"${CLAUDE_PROJECT_DIR:-.}\" 2>/dev/null && [ -f scripts/claude_usage.py ] && python3 scripts/claude_usage.py update --quiet >/dev/null 2>&1; exit 0",
          "timeout": 60
        }
      ]
    }
  ]
}
```

It prints nothing, always exits 0 so it can never fail a session, and does nothing on a branch that does not have the
script. It leaves `ledger.json` and `SUMMARY.md` modified in the working tree; it never commits. Check that it ran with
`git status` after a session.
