#!/usr/bin/env python3
"""Collects and tracks the Claude Code usage of this project.

    python scripts/claude_usage.py report [--transcripts DIR] [--ledger FILE]
        Prints the tokens used and what they would cost at API list prices, from the Claude Code transcripts on this
        machine merged with the ledger. Changes nothing.

    python scripts/claude_usage.py update [--transcripts DIR] [--ledger FILE] [--summary FILE]
        Merges the transcripts into the ledger (aidlc-docs/claude-usage/ledger.json) and rewrites the readable summary
        next to it (SUMMARY.md). Run it before a pull request or a release and commit the two files.

Why a ledger: Claude Code keeps its transcripts only on the machine that ran it and does not keep them for ever, so
usage that is only in the transcripts is lost. The ledger holds one row per session, day, model and kind (main or
subagent) and only ever grows: a number is never lowered, and a row whose transcript has gone is kept.

Only token counts and ids are read from a transcript, never what was said in it. The ledger is safe to commit: it has
session ids, dates, model names and counts, nothing else.

Only the standard library, and syntax from Python 3.9 on, so it runs anywhere.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = REPO_ROOT / "aidlc-docs" / "claude-usage" / "ledger.json"
DEFAULT_SUMMARY = REPO_ROOT / "aidlc-docs" / "claude-usage" / "SUMMARY.md"
PRICES_FILE = Path(__file__).resolve().parent / "claude_usage_prices.json"

LEDGER_VERSION = 1
KEY_FIELDS = ("session", "day", "model", "kind")
COUNT_FIELDS = (
    "requests",
    "input",
    "output",
    "thinking",
    "cache_read",
    "cache_write_5m",
    "cache_write_1h",
    "advisor_requests",
)
MILLION = 1_000_000


def default_transcript_dir(repo_root: Path = REPO_ROOT, home: Optional[Path] = None) -> Path:
    """Where Claude Code keeps this project's transcripts: its folder name is the project path with every character
    that is not a letter or a digit turned into a dash."""
    return (home or Path.home()) / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(repo_root))


def iter_transcripts(directory: Path) -> Iterator[Tuple[Path, str, str]]:
    """(file, session id, kind) for every transcript: the sessions themselves, and their subagents' files in
    <session>/subagents/, which are counted as the session's own usage but kept apart as kind "subagent"."""
    if not directory.is_dir():
        return
    for path in sorted(directory.glob("*.jsonl")):
        yield path, path.stem, "main"
    for path in sorted(directory.glob("*/subagents/*.jsonl")):
        yield path, path.parent.parent.name, "subagent"


def _int(value) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def read_requests(path: Path) -> Dict[Tuple[str, str], dict]:
    """One record per API request in a transcript.

    Claude Code writes a line per content block of a response, and each repeats the request's usage; the input and
    cache counts are the same on every line but the output count grows while the response streams. So a request is
    one (message id, request id) however many lines it has, and each count is the largest seen. Lines that are not
    assistant responses with usage, and the placeholder responses Claude Code writes for failed requests
    (model "<synthetic>"), are not usage."""
    requests: Dict[Tuple[str, str], dict] = {}
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict) or entry.get("type") != "assistant":
                continue
            message = entry.get("message")
            usage = message.get("usage") if isinstance(message, dict) else None
            model = message.get("model") if isinstance(message, dict) else None
            if not isinstance(usage, dict) or not isinstance(model, str) or model.startswith("<"):
                continue
            message_id = message.get("id")
            if not message_id:
                continue
            key = (message_id, entry.get("requestId") or "")
            created = usage.get("cache_creation") if isinstance(usage.get("cache_creation"), dict) else {}
            written = _int(usage.get("cache_creation_input_tokens"))
            write_1h = _int(created.get("ephemeral_1h_input_tokens"))
            # Without a breakdown by lifetime, the cheaper five-minute rate is assumed for the whole write.
            write_5m = max(_int(created.get("ephemeral_5m_input_tokens")), written - write_1h)
            details = usage.get("output_tokens_details") if isinstance(usage.get("output_tokens_details"), dict) else {}
            seen = {
                "input": _int(usage.get("input_tokens")),
                "output": _int(usage.get("output_tokens")),
                "thinking": _int(details.get("thinking_tokens")),
                "cache_read": _int(usage.get("cache_read_input_tokens")),
                "cache_write_5m": write_5m,
                "cache_write_1h": write_1h,
            }
            timestamp = entry.get("timestamp") if isinstance(entry.get("timestamp"), str) else ""
            record = requests.get(key)
            if record is None:
                requests[key] = dict(seen, model=model, day=timestamp[:10], advisor=bool(entry.get("advisorModel")))
                continue
            for field, value in seen.items():
                record[field] = max(record[field], value)
            if timestamp and (not record["day"] or timestamp[:10] < record["day"]):
                record["day"] = timestamp[:10]
            record["advisor"] = record["advisor"] or bool(entry.get("advisorModel"))
    return requests


def collect(directory: Path) -> List[dict]:
    """Ledger rows for every transcript under `directory`."""
    rows: Dict[Tuple[str, str, str, str], dict] = {}
    for path, session, kind in iter_transcripts(directory):
        for record in read_requests(path).values():
            if not record["day"]:
                continue
            key = (session, record["day"], record["model"], kind)
            row = rows.setdefault(key, dict(zip(KEY_FIELDS, key), **{field: 0 for field in COUNT_FIELDS}))
            row["requests"] += 1
            row["advisor_requests"] += 1 if record["advisor"] else 0
            for field in ("input", "output", "thinking", "cache_read", "cache_write_5m", "cache_write_1h"):
                row[field] += record[field]
    return sorted(rows.values(), key=_row_key)


def _row_key(row: dict) -> Tuple[str, str, str, str]:
    return tuple(row[field] for field in KEY_FIELDS)  # type: ignore[return-value]


def load_ledger(path: Path) -> List[dict]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != LEDGER_VERSION:
        raise ValueError("{}: unknown ledger version {!r}".format(path, data.get("version")))
    return data["rows"]


def merge(ledger_rows: List[dict], live_rows: List[dict]) -> List[dict]:
    """The ledger with the live rows folded in. A row's counts only ever grow (the larger of the two is kept), and a
    row that exists only in the ledger, because its transcript has gone, is kept as it is."""
    merged: Dict[Tuple[str, str, str, str], dict] = {_row_key(row): dict(row) for row in ledger_rows}
    for row in live_rows:
        current = merged.get(_row_key(row))
        if current is None:
            merged[_row_key(row)] = dict(row)
            continue
        for field in COUNT_FIELDS:
            current[field] = max(current.get(field, 0), row[field])
    return sorted(merged.values(), key=_row_key)


def write_ledger(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"version": LEDGER_VERSION, "rows": [{**{k: row[k] for k in KEY_FIELDS}, **{k: row[k] for k in COUNT_FIELDS}} for row in rows]}
    path.write_text(json.dumps(body, indent=1) + "\n", encoding="utf-8")


def load_prices(path: Path = PRICES_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def cost(row: dict, prices: dict) -> Optional[float]:
    """What a row's tokens cost at list prices, or None when its model has no price in the prices file."""
    rate = prices["models"].get(row["model"])
    if rate is None:
        return None
    return (
        row["input"] * rate["input"]
        + row["output"] * rate["output"]
        + row["cache_read"] * rate["cache_read"]
        + row["cache_write_5m"] * rate["cache_write_5m"]
        + row["cache_write_1h"] * rate["cache_write_1h"]
    ) / MILLION


def cost_by_type(rows: List[dict], prices: dict) -> Dict[str, float]:
    """The cost of the priced rows split into fresh input, output, cache reads and cache writes."""
    parts = {"input": 0.0, "output": 0.0, "cache_read": 0.0, "cache_write": 0.0}
    for row in rows:
        rate = prices["models"].get(row["model"])
        if rate is None:
            continue
        parts["input"] += row["input"] * rate["input"] / MILLION
        parts["output"] += row["output"] * rate["output"] / MILLION
        parts["cache_read"] += row["cache_read"] * rate["cache_read"] / MILLION
        parts["cache_write"] += (row["cache_write_5m"] * rate["cache_write_5m"] + row["cache_write_1h"] * rate["cache_write_1h"]) / MILLION
    return parts


def _totals(rows: List[dict], prices: dict) -> dict:
    total = {field: sum(row[field] for row in rows) for field in COUNT_FIELDS}
    costs = [cost(row, prices) for row in rows]
    total["cost"] = sum(c for c in costs if c is not None)
    total["unpriced_requests"] = sum(row["requests"] for row, c in zip(rows, costs) if c is None)
    return total


def _tokens(value: int) -> str:
    return "{:,}".format(value)


def _usd(value: float) -> str:
    return "${:,.2f}".format(value)


def repository_start_day(root: Path = REPO_ROOT) -> Optional[str]:
    """The day of the repository's first commit, or None when git cannot say."""
    try:
        out = subprocess.run(
            ["git", "log", "--reverse", "--format=%aI"], cwd=str(root), capture_output=True, text=True, timeout=30
        ).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return None
    return out[0][:10] if out else None


def render(rows: List[dict], prices: dict, repo_start: Optional[str] = None) -> str:
    """The report as Markdown (it is also what is printed)."""
    if not rows:
        return "No Claude Code usage found: no transcripts and an empty ledger.\n"
    total = _totals(rows, prices)
    first, last = min(row["day"] for row in rows), max(row["day"] for row in rows)
    sessions = {row["session"] for row in rows}
    lines = [
        "# Claude Code usage of this project",
        "",
        "Collected by `scripts/claude_usage.py` from Claude Code's own transcripts into `ledger.json`. "
        "Days are UTC. Data through **{}**.".format(last),
        "",
        "| | |",
        "|---|---|",
        "| Estimated cost at API list prices | **{}** (a floor, see below) |".format(_usd(total["cost"])),
        "| API requests | {} in {} sessions, {} to {} |".format(_tokens(total["requests"]), len(sessions), first, last),
        "",
        "## Where the cost goes",
        "",
        "| Tokens | Count | Est. cost | Share |",
        "|---|---:|---:|---:|",
    ]
    parts = cost_by_type(rows, prices)
    spent = sum(parts.values()) or 1.0
    for label, count, key in (
        ("Cache reads (the conversation so far, re-read every turn)", total["cache_read"], "cache_read"),
        ("Cache writes (new context stored)", total["cache_write_5m"] + total["cache_write_1h"], "cache_write"),
        ("Output (of which thinking {})".format(_tokens(total["thinking"])), total["output"], "output"),
        ("Fresh input", total["input"], "input"),
    ):
        lines.append("| {} | {} | {} | {:.0f}% |".format(label, _tokens(count), _usd(parts[key]), 100 * parts[key] / spent))
    lines += [
        "",
        "## By model",
        "",
        "| Model | Requests | Output | Cache read | Cache write | Est. cost |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    by_model: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        by_model[row["model"]].append(row)
    for model in sorted(by_model, key=lambda m: -_totals(by_model[m], prices)["cost"]):
        t = _totals(by_model[model], prices)
        priced = prices["models"].get(model) is not None
        lines.append(
            "| `{}` | {} | {} | {} | {} | {} |".format(
                model,
                _tokens(t["requests"]),
                _tokens(t["output"]),
                _tokens(t["cache_read"]),
                _tokens(t["cache_write_5m"] + t["cache_write_1h"]),
                _usd(t["cost"]) if priced else "not priced",
            )
        )
    lines += ["", "## By month", "", "| Month | Sessions | Requests | Output | Est. cost |", "|---|---:|---:|---:|---:|"]
    by_month: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        by_month[row["day"][:7]].append(row)
    for month in sorted(by_month):
        t = _totals(by_month[month], prices)
        lines.append(
            "| {} | {} | {} | {} | {} |".format(
                month, len({r["session"] for r in by_month[month]}), _tokens(t["requests"]), _tokens(t["output"]), _usd(t["cost"])
            )
        )
    lines += ["", "## By session", "", "| Session | From | To | Requests | Subagent share | Est. cost |", "|---|---|---|---:|---:|---:|"]
    by_session: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        by_session[row["session"]].append(row)
    for session in sorted(by_session, key=lambda s: min(r["day"] for r in by_session[s])):
        group = by_session[session]
        t = _totals(group, prices)
        sub = sum(c for r in group if r["kind"] == "subagent" for c in [cost(r, prices) or 0.0])
        share = "{:.0f}%".format(100 * sub / t["cost"]) if t["cost"] else "-"
        lines.append(
            "| `{}` | {} | {} | {} | {} | {} |".format(
                session[:8], min(r["day"] for r in group), max(r["day"] for r in group), _tokens(t["requests"]), share, _usd(t["cost"])
            )
        )
    cal = prices.get("calibration", {})
    lines += ["", "## What these numbers are, and are not", ""]
    lines.append(
        "- **An estimate of API-equivalent cost, not a bill.** Tokens are priced at Anthropic's list prices "
        "(`scripts/claude_usage_prices.json`, as of {}), today's prices applied to every date; a subscription plan is billed "
        "differently.".format(prices.get("as_of", "?"))
    )
    if cal:
        lines.append(
            "- **A floor.** On the one session where Claude Code recorded its own cost, this method came out {}% to {}% "
            "below it: Claude Code also counts calls the transcripts do not record. The prices themselves reproduce "
            "Claude Code's figure exactly for the same tokens (checked {}).".format(
                cal.get("shortfall_low_percent"), cal.get("shortfall_high_percent"), cal.get("checked_on")
            )
        )
    advisor = total["advisor_requests"]
    if advisor:
        lines.append(
            "- **Advisor calls are not counted.** {} requests consulted a stronger advisor model; the transcripts record "
            "that it was consulted but not its tokens, so whatever it used is missing.".format(_tokens(advisor))
        )
    if total["unpriced_requests"]:
        lines.append(
            "- **{} requests are of a model with no price** in the prices file and are left out of the cost.".format(
                _tokens(total["unpriced_requests"])
            )
        )
    if repo_start and first > repo_start:
        lines.append(
            "- **Not complete: nothing before {}.** The repository's first commit is on {}, but the earliest transcript "
            "found is from {}; the sessions in between, and any run on another machine, are not in the ledger.".format(
                first, repo_start, first
            )
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("report", "print the usage"), ("update", "merge the transcripts into the ledger")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--transcripts", type=Path, default=None, help="Claude Code's transcript folder for this project")
        p.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
        if name == "update":
            p.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args(argv)

    directory = args.transcripts or default_transcript_dir()
    live = collect(directory)
    existing = load_ledger(args.ledger)
    rows = merge(existing, live)
    prices = load_prices()
    text = render(rows, prices, repository_start_day())
    if args.command == "report":
        if not directory.is_dir():
            print("note: no transcripts at {}; showing the ledger only".format(directory), file=sys.stderr)
        sys.stdout.write(text)
        return 0
    write_ledger(args.ledger, rows)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(text, encoding="utf-8")
    print(
        "claude usage: {} ledger rows ({} read from transcripts, {} already in the ledger); wrote {} and {}".format(
            len(rows), len(live), len(existing), args.ledger, args.summary
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
