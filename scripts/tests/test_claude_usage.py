"""Claude Code usage of this project is collected into a ledger that only ever grows."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import claude_usage  # noqa: E402

PRICES = claude_usage.load_prices()


def assistant(message_id, request_id="req_1", model="claude-sonnet-5-5", timestamp="2026-10-01T10:00:00.000Z", **usage):
    usage.setdefault("input_tokens", 2)
    usage.setdefault("output_tokens", 10)
    usage.setdefault("cache_read_input_tokens", 1000)
    usage.setdefault("cache_creation_input_tokens", 0)
    entry = {
        "type": "assistant",
        "timestamp": timestamp,
        "requestId": request_id,
        "message": {"id": message_id, "model": model, "usage": usage},
    }
    return json.dumps(entry)


def write_transcript(path: Path, *lines: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def only(rows, **match):
    found = [row for row in rows if all(row[k] == v for k, v in match.items())]
    assert len(found) == 1, found
    return found[0]


def test_a_streamed_response_is_one_request_with_the_largest_output(tmp_path):
    # One response is written as a line per content block; the input and cache counts repeat, the output grows.
    write_transcript(
        tmp_path / "s1.jsonl",
        assistant("m1", output_tokens=4),
        assistant("m1", output_tokens=172),
        assistant("m1", output_tokens=90),
        assistant("m2", request_id="req_2", output_tokens=5),
    )
    row = only(claude_usage.collect(tmp_path), session="s1")
    assert row["requests"] == 2
    assert row["output"] == 172 + 5
    assert row["input"] == 2 + 2
    assert row["cache_read"] == 1000 + 1000


def test_lines_that_are_not_usage_are_ignored(tmp_path):
    write_transcript(
        tmp_path / "s1.jsonl",
        "this is not json",
        json.dumps({"type": "user", "message": {"content": "hello"}}),
        assistant("synthetic", model="<synthetic>", output_tokens=0),
        json.dumps({"type": "assistant", "message": {"id": "no_usage", "model": "claude-sonnet-5-5"}}),
        assistant("m1"),
    )
    rows = claude_usage.collect(tmp_path)
    assert len(rows) == 1 and rows[0]["requests"] == 1


def test_subagent_files_count_for_their_session_but_as_their_own_kind(tmp_path):
    write_transcript(tmp_path / "s1.jsonl", assistant("m1"))
    write_transcript(tmp_path / "s1" / "subagents" / "agent-abc.jsonl", assistant("sub1", request_id="req_s", output_tokens=50))
    rows = claude_usage.collect(tmp_path)
    assert only(rows, session="s1", kind="main")["output"] == 10
    sub = only(rows, session="s1", kind="subagent")
    assert sub["output"] == 50 and sub["requests"] == 1


def test_a_day_is_the_utc_day_of_the_first_line_of_a_request(tmp_path):
    write_transcript(
        tmp_path / "s1.jsonl",
        assistant("m1", timestamp="2026-10-01T23:59:59.000Z", output_tokens=1),
        assistant("m1", timestamp="2026-10-02T00:00:02.000Z", output_tokens=9),
        assistant("m2", request_id="req_2", timestamp="2026-10-02T00:05:00.000Z"),
    )
    rows = claude_usage.collect(tmp_path)
    assert only(rows, day="2026-10-01")["output"] == 9
    assert only(rows, day="2026-10-02")["requests"] == 1


def test_cache_writes_are_split_by_lifetime_and_default_to_the_cheaper_five_minutes(tmp_path):
    write_transcript(
        tmp_path / "s1.jsonl",
        assistant("m1", cache_creation_input_tokens=300, cache_creation={"ephemeral_1h_input_tokens": 300, "ephemeral_5m_input_tokens": 0}),
        assistant("m2", request_id="req_2", cache_creation_input_tokens=100),
    )
    row = only(claude_usage.collect(tmp_path), session="s1")
    assert row["cache_write_1h"] == 300
    assert row["cache_write_5m"] == 100


def test_requests_that_consulted_the_advisor_are_counted_but_not_priced(tmp_path):
    entry = json.loads(assistant("m1"))
    entry["advisorModel"] = "claude-opus-5-5"
    write_transcript(tmp_path / "s1.jsonl", json.dumps(entry), assistant("m2", request_id="req_2"))
    assert only(claude_usage.collect(tmp_path), session="s1")["advisor_requests"] == 1


def test_the_prices_reproduce_the_cost_claude_code_itself_recorded(tmp_path):
    # Claude Code's own cost-state record: $17.7706 for exactly these tokens, all of them one-hour cache writes.
    row = {
        "model": "claude-sonnet-5-5",
        "input": 6824,
        "output": 228619,
        "cache_read": 45036636,
        "cache_write_5m": 0,
        "cache_write_1h": 1615857,
    }
    assert round(claude_usage.cost(row, PRICES), 4) == 17.7706


def test_a_model_without_a_price_has_no_cost_and_is_said_so(tmp_path):
    write_transcript(tmp_path / "s1.jsonl", assistant("m1", model="claude-future-9"))
    rows = claude_usage.collect(tmp_path)
    assert claude_usage.cost(rows[0], PRICES) is None
    text = claude_usage.render(rows, PRICES)
    assert "not priced" in text and "no price" in text


def test_the_ledger_only_grows_and_keeps_rows_whose_transcripts_are_gone(tmp_path):
    key = dict(session="old", day="2026-08-20", model="claude-sonnet-5", kind="main")
    zero = {field: 0 for field in claude_usage.COUNT_FIELDS}
    purged = dict(key, **dict(zero, requests=7, output=700))
    shrunk = dict(session="s1", day="2026-10-01", model="claude-sonnet-5-5", kind="main", **dict(zero, requests=5, output=500))
    live_shrunk = dict(shrunk, **dict(zero, requests=3, output=900))
    new = dict(session="s2", day="2026-10-02", model="claude-sonnet-5-5", kind="main", **dict(zero, requests=1, output=10))

    merged = claude_usage.merge([purged, shrunk], [live_shrunk, new])

    assert only(merged, session="old")["output"] == 700
    assert only(merged, session="s1")["requests"] == 5 and only(merged, session="s1")["output"] == 900
    assert only(merged, session="s2")["output"] == 10


def test_update_is_repeatable_and_writes_the_ledger_and_summary(tmp_path, capsys):
    transcripts = tmp_path / "transcripts"
    write_transcript(transcripts / "s1.jsonl", assistant("m1", output_tokens=40))
    ledger, summary = tmp_path / "out" / "ledger.json", tmp_path / "out" / "SUMMARY.md"
    args = ["update", "--transcripts", str(transcripts), "--ledger", str(ledger), "--summary", str(summary)]

    assert claude_usage.main(args) == 0
    first = ledger.read_bytes()
    assert claude_usage.main(args) == 0

    assert ledger.read_bytes() == first
    assert "Claude Code usage of this project" in summary.read_text()
    data = json.loads(first)
    assert data["version"] == 1 and data["rows"][0]["output"] == 40


def test_a_report_after_the_transcripts_are_gone_still_shows_the_ledger(tmp_path, capsys):
    transcripts = tmp_path / "transcripts"
    write_transcript(transcripts / "s1.jsonl", assistant("m1", output_tokens=40))
    ledger = tmp_path / "ledger.json"
    claude_usage.main(["update", "--transcripts", str(transcripts), "--ledger", str(ledger), "--summary", str(tmp_path / "S.md")])
    capsys.readouterr()

    claude_usage.main(["report", "--transcripts", str(tmp_path / "gone"), "--ledger", str(ledger)])

    assert "Output (of which thinking 0) | 40 " in capsys.readouterr().out


def test_the_ledger_has_no_conversation_content(tmp_path):
    secret = "the password is hunter2"
    entry = json.loads(assistant("m1"))
    entry["message"]["content"] = [{"type": "text", "text": secret}]
    write_transcript(tmp_path / "s1.jsonl", json.dumps(entry))
    ledger = tmp_path / "ledger.json"
    claude_usage.write_ledger(ledger, claude_usage.collect(tmp_path))
    assert secret not in ledger.read_text()


def test_the_transcript_folder_name_is_the_project_path_with_dashes():
    path = claude_usage.default_transcript_dir(Path("/Users/jax/projects/transact.Agent_x"), home=Path("/h"))
    assert path == Path("/h/.claude/projects/-Users-jax-projects-transact-Agent-x")
