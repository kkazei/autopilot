"""Critic calibration script (D2-B): CSV validation, the numbers in the report, quota limits and failures.

MockLLM and temp data dirs only: nothing here calls a model. The real run is `python -m evals.calibrate_critic`.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import date
from pathlib import Path

import pytest

from evals import calibrate_critic as cal
from harness import guardrails, quota, trace
from harness.llm import LLMAuthError, LLMConfigError, LLMResponse, LLMUnavailable, MockLLM
from harness.schemas import CRITIQUE_DIMENSIONS
from tests.helpers import NOW, data  # noqa: F401

@pytest.fixture(autouse=True)
def isolated_data(data):  # noqa: F811
    """Every test here writes traces and reads the daily count, so none may touch the real data/ folder."""
    return data


COLUMNS = ["draft_id", "text", "my_voice", "my_clarity", "my_cta", "my_policy", "topic", "angle", "goal"]
DAY = date(2026, 10, 23)


def crit(voice=5, clarity=5, cta=5, policy_risk=5) -> str:
    scores = {"voice": voice, "clarity": clarity, "cta": cta, "policy_risk": policy_risk}
    return json.dumps({**scores, "reasons": {d: f"reason-{d}-{v}" for d, v in scores.items()}})


def write_csv(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({c: r.get(c, "") for c in COLUMNS} for r in rows)
    return path


def row(draft_id, human=None, text=None, **extra) -> dict:
    scores = dict(zip(("my_voice", "my_clarity", "my_cta", "my_policy"), human or ("", "", "", "")))
    return {"draft_id": draft_id, "text": text or f"Saturday class draft {draft_id}. https://example.com/bramblewick/classes",
            **scores, **extra}


def run(tmp_path, rows, script, *extra, now=NOW):
    out: list[str] = []
    csv_path = write_csv(tmp_path / "drafts.csv", rows)
    llm = script if isinstance(script, MockLLM) else MockLLM(list(script))
    code = cal.main(["--csv", str(csv_path), "--out", str(tmp_path / "report.md"), *extra],
                    llm=llm, now=now, say=out.append, env_file=None)
    return code, llm, "\n".join(out)


# ---------- the shipped file ----------

def test_the_shipped_csv_has_ten_valid_drafts_whether_or_not_the_scores_are_filled_in():
    rows = cal.read_rows(cal.DEFAULT_CSV, DAY)  # raises on any bad score, so a scored file must stay valid too
    assert [r.draft_id for r in rows] == [f"d{i:02d}" for i in range(1, 11)]
    assert all(r.human is None or set(r.human) == set(CRITIQUE_DIMENSIONS) for r in rows)  # blank, or all four
    assert all(len(r.text) <= 300 for r in rows)
    brief = json.loads((cal.trace.REPO_ROOT / "data" / "brand_brief.json").read_text(encoding="utf-8"))
    banned = {r.draft_id for r in rows if not guardrails.check_banned(r.text, brief)["ok"]}
    assert banned == {"d07"}  # the deliberate banned-phrase draft is caught by the real guardrail; no other draft is
    assert len({r.planned.topic for r in rows}) > 1  # topics vary, so topic fit is exercised


# ---------- validation ----------

@pytest.mark.parametrize("bad, message", [
    ({"my_voice": "6", "my_clarity": "4", "my_cta": "4", "my_policy": "4"}, "from 1 to 5"),
    ({"my_voice": "x", "my_clarity": "4", "my_cta": "4", "my_policy": "4"}, "whole number"),
    ({"my_voice": "4", "my_clarity": "4"}, "all four"),
    ({"text": ""}, "text"),
    ({"text": "x" * 301}, "300"),
    ({"goal": "shout"}, "goal"),
    ({"draft_id": ""}, "draft_id is empty"),
])
def test_a_bad_row_is_refused_before_any_model_call(tmp_path, bad, message):
    code, llm, out = run(tmp_path, [row("a", (4, 4, 4, 4)), {**row("b"), **bad}], [crit()])
    assert code == cal.EXIT_REFUSED and llm.calls == [] and message in out and "line 3" in out


def test_duplicate_ids_a_missing_column_and_an_empty_file_are_refused(tmp_path):
    assert run(tmp_path, [row("a"), row("a")], [])[0] == cal.EXIT_REFUSED
    (tmp_path / "bad.csv").write_text("draft_id,text\na,hello\n", encoding="utf-8")
    with pytest.raises(cal.CalibrationError, match="missing columns: my_voice"):
        cal.read_rows(tmp_path / "bad.csv", DAY)
    (tmp_path / "empty.csv").write_text(",".join(COLUMNS) + "\n", encoding="utf-8")
    with pytest.raises(cal.CalibrationError, match="no rows"):
        cal.read_rows(tmp_path / "empty.csv", DAY)


def test_blank_topic_angle_and_goal_fall_back_to_the_default_planned_post(tmp_path):
    [r] = cal.read_rows(write_csv(tmp_path / "d.csv", [row("a")]), DAY)
    assert (r.planned.topic, r.planned.goal) == (cal.DEFAULT_PLAN["topic"], "click")
    [r] = cal.read_rows(write_csv(tmp_path / "e.csv", [row("a", topic="Rye", angle="crust", goal="awareness")]), DAY)
    assert (r.planned.topic, r.planned.angle, r.planned.goal) == ("Rye", "crust", "awareness")


# ---------- the numbers ----------

HUMAN = {"a": (5, 5, 5, 5), "b": (2, 2, 2, 2), "c": (4, 4, 4, 4), "d": (3, 3, 3, 3)}
CRITIC = [crit(5, 5, 5, 5), crit(5, 5, 5, 5), crit(4, 3, 4, 4), crit(3, 3, 3, 3)]


def four_rows():
    return [row(k, v) for k, v in HUMAN.items()]


def test_the_report_has_the_exact_error_agreement_and_disagreement_numbers(tmp_path):
    code, llm, out = run(tmp_path, four_rows(), CRITIC)
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert code == cal.EXIT_OK and len(llm.calls) == 4 and report in out
    # mean absolute error: voice 0,3,0,0; clarity 0,3,1,0; cta 0,3,0,0; policy 0,3,0,0
    assert "| voice | 0.75 | +0.75 |" in report and "| clarity | 1.00 | +0.50 |" in report
    assert "| cta | 0.75 | +0.75 |" in report and "| policy_risk | 0.75 | +0.75 |" in report
    # you / critic pass: a pass/pass, b fail/pass (too lenient), c pass/fail (too strict), d fail/fail
    assert "**2 of 4** (50%)" in report
    assert "too lenient): 1 (b)" in report and "too strict): 1 (c)" in report
    top = report.split("biggest disagreements")[1].split("## Every draft")[0]
    assert top.index("| b |") < top.index("| c |") and "| a |" not in top and "| d |" not in top
    assert "**voice**: reason-voice-5" in top  # the critic's own reason, for a dimension where you differ
    c_line = next(line for line in top.splitlines() if line.startswith("| c |"))
    assert "reason-clarity-3" in c_line and "reason-voice" not in c_line  # only the dimensions that differ


def test_only_the_three_biggest_disagreements_are_listed(tmp_path):
    rows = [row(f"x{i}", (5, 5, 5, 5)) for i in range(5)]
    code, _, out = run(tmp_path, rows, [crit(5 - i, 5, 5, 5) for i in range(5)])  # gaps 0,1,2,3,4
    top = out.split("biggest disagreements")[1].split("## Every draft")[0]
    assert [line.split("|")[1].strip() for line in top.splitlines() if line.startswith("| x")] == ["x4", "x3", "x2"]


def test_a_perfect_match_says_so(tmp_path):
    _, _, out = run(tmp_path, [row("a", (5, 4, 5, 5))], [crit(5, 4, 5, 5)])
    assert "None: the critic matched your score on every dimension" in out and "**1 of 1** (100%)" in out


def test_the_threshold_flag_changes_what_counts_as_a_pass(tmp_path):
    _, _, out = run(tmp_path, [row("a", (4, 4, 4, 4))], [crit(4, 4, 4, 4)], "--min-score", "5")
    assert "at least 5" in out and "a | 4 / 4 / 4 / 4 | 4 / 4 / 4 / 4 | fail / fail" in out


def test_pipes_and_newlines_in_a_draft_do_not_break_the_tables(tmp_path):
    text = "Rye | wheat\nand more https://example.com/bramblewick/classes"
    _, _, out = run(tmp_path, [row("a", (2, 2, 2, 2), text=text)], [crit(5, 5, 5, 5)])
    line = next(ln for ln in out.splitlines() if ln.startswith("| a | Rye"))
    assert "Rye \\| wheat and more" in line
    assert len(re.findall(r"(?<!\\)\|", line)) == 6  # five cells, so only the six cell borders are bare pipes


# ---------- models, temperature, failures ----------

def test_a_fallback_model_is_recorded_per_draft_and_warned_about(tmp_path):
    script = [LLMResponse(model="a/one:free", content=crit()), LLMResponse(model="b/two:free", content=crit())]
    _, _, out = run(tmp_path, [row("a", (5, 5, 5, 5)), row("b", (5, 5, 5, 5))], script)
    assert "Scored by: a/one:free, b/two:free" in out and "more than one model answered" in out
    assert "| a | 5 / 5 / 5 / 5 | 5 / 5 / 5 / 5 | pass / pass | a/one:free |" in out
    assert "| b | 5 / 5 / 5 / 5 | 5 / 5 / 5 / 5 | pass / pass | b/two:free |" in out


def test_the_real_client_is_built_with_temperature_zero(tmp_path, monkeypatch):
    built: list[dict] = []

    def fake_client(**kwargs):
        built.append(kwargs)
        return MockLLM([crit()])

    monkeypatch.setattr(cal, "OpenRouterLLM", fake_client)
    csv_path = write_csv(tmp_path / "d.csv", [row("a", (5, 5, 5, 5))])
    assert cal.main(["--csv", str(csv_path), "--out", str(tmp_path / "r.md")], now=NOW, say=lambda s: None,
                    env_file=None) == cal.EXIT_OK
    assert built == [{"temperature": 0.0}]


def test_a_missing_key_is_refused_without_a_model_call(tmp_path, monkeypatch):
    def broken(**kwargs):
        raise LLMConfigError("OPENROUTER_API_KEY is not set")

    monkeypatch.setattr(cal, "OpenRouterLLM", broken)
    csv_path = write_csv(tmp_path / "d.csv", [row("a", (5, 5, 5, 5))])
    out: list[str] = []
    assert cal.main(["--csv", str(csv_path)], now=NOW, say=out.append, env_file=None) == cal.EXIT_REFUSED
    assert any("OPENROUTER_API_KEY is not set" in line for line in out)


def test_a_reply_that_stays_invalid_fails_that_draft_only(tmp_path):
    rows = [row("a", (5, 5, 5, 5)), row("b", (5, 5, 5, 5)), row("c", (5, 5, 5, 5))]
    code, llm, out = run(tmp_path, rows, [crit(), "not json", "still not json", crit()])
    assert code == cal.EXIT_INCOMPLETE and len(llm.calls) == 4  # one repair for b, then c still ran
    assert "## Not scored" in out and "- b: LLMOutputError" in out
    assert "| a | 5 / 5 / 5 / 5 | 5 / 5 / 5 / 5 |" in out and "| c | 5 / 5 / 5 / 5 | 5 / 5 / 5 / 5 |" in out


def test_an_unavailable_chain_stops_the_run_instead_of_asking_for_every_draft(tmp_path):
    from harness.llm import LLMUnavailable

    rows = [row(c, (5, 5, 5, 5)) for c in "abcd"]
    code, llm, out = run(tmp_path, rows, [crit(), LLMUnavailable("all 3 models failed"), crit(), crit()])
    assert code == cal.EXIT_INCOMPLETE and len(llm.calls) == 2  # c and d were never requested
    assert "Stopped early" in out and "- c: not attempted" in out and "- d: not attempted" in out


# ---------- quota ----------

def test_no_scores_yet_refuses_without_a_model_call_unless_allowed(tmp_path):
    code, llm, out = run(tmp_path, [row("a"), row("b")], [crit(), crit()])
    assert code == cal.EXIT_REFUSED and llm.calls == [] and "--allow-unscored" in out
    code, llm, out = run(tmp_path, [row("a"), row("b")], [crit(), crit()], "--allow-unscored")
    assert code == cal.EXIT_OK and len(llm.calls) == 2 and "nothing to compare" in out


def test_check_validates_and_plans_without_any_model_call(tmp_path):
    code, llm, out = run(tmp_path, [row("a"), row("b", (4, 4, 4, 4))], [crit()], "--check")
    assert code == cal.EXIT_OK and llm.calls == [] and "2 drafts, 1 with your scores" in out and "no model calls" in out


def test_an_exhausted_daily_guard_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr(quota, "llm_calls_since", lambda since: (quota.DAILY_REQUEST_LIMIT, 0))
    code, llm, out = run(tmp_path, [row("a", (5, 5, 5, 5))], [crit()])
    assert code == cal.EXIT_REFUSED and llm.calls == [] and "no requests left" in out


def test_the_request_cap_is_what_is_left_today_and_stops_the_run_cleanly(tmp_path, monkeypatch):
    monkeypatch.setattr(quota, "llm_calls_since", lambda since: (quota.DAILY_REQUEST_LIMIT - 2, 0))  # 2 left
    rows = [row(c, (5, 5, 5, 5)) for c in "abcd"]
    code, llm, out = run(tmp_path, rows, [crit()] * 4, "--max-requests", "99")  # asking for more changes nothing
    assert code == cal.EXIT_INCOMPLETE and len(llm.calls) == 2
    assert "up to 2 requests" in out and "some will not be scored" in out and "Stopped early" in out


def test_the_calibration_requests_are_traced_so_the_daily_guard_counts_them(tmp_path):
    run(tmp_path, [row("a", (5, 5, 5, 5)), row("b", (5, 5, 5, 5))], [crit(), crit()])
    used, unreadable = quota.llm_calls_since(NOW - quota.WINDOW)
    assert (used, unreadable) == (2, 0)
    [run_file] = (trace.data_dir() / "runs").glob("run_*.json")
    assert all(e.agent == "critic" for e in trace.read_run(run_file.stem) if e.kind == "llm_call")


# ---------- stopping, partial reports and rows without scores ----------

def test_a_refused_key_stops_the_run_after_one_call_and_still_saves_a_report(tmp_path):
    rows = [row(c, (5, 5, 5, 5)) for c in "abcde"]
    code, llm, out = run(tmp_path, rows, [LLMAuthError("openai: HTTP 401: bad key")] * 5)
    assert code == cal.EXIT_INCOMPLETE and len(llm.calls) == 1  # not one call per draft
    assert "Stopped early" in out and "LLMAuthError" in out
    assert all(f"- {c}: not attempted" in out for c in "bcde")
    assert not (tmp_path / "report.md").exists()  # a partial report never takes the real report's place
    [partial] = tmp_path.glob("report.partial-*.md")
    assert partial.read_text(encoding="utf-8") in out


def test_drafts_scored_before_a_stop_are_kept_in_the_report(tmp_path):
    rows = [row(c, (5, 5, 5, 5)) for c in "abc"]
    code, llm, out = run(tmp_path, rows, [crit(), crit(4, 4, 4, 4), LLMAuthError("HTTP 402: no credits")])
    assert code == cal.EXIT_INCOMPLETE and len(llm.calls) == 3
    assert "| a | 5 / 5 / 5 / 5 | 5 / 5 / 5 / 5 |" in out and "| b | 5 / 5 / 5 / 5 | 4 / 4 / 4 / 4 |" in out
    assert "2 scored by the critic" in out and "- c: not scored: LLMAuthError" in out


def test_a_trace_that_cannot_be_written_stops_the_run_with_a_partial_report(tmp_path):
    rows = [row(c, (5, 5, 5, 5)) for c in "abc"]
    code, llm, out = run(tmp_path, rows, [crit(), trace.TraceWriteError("trace write failed: disk full"), crit()])
    assert code == cal.EXIT_INCOMPLETE and len(llm.calls) == 2
    assert "Stopped early" in out and "TraceWriteError" in out and "| a | 5 / 5 / 5 / 5 | 5 / 5 / 5 / 5 |" in out


def test_ctrl_c_stops_the_run_and_keeps_what_was_scored(tmp_path, monkeypatch):
    real, calls = cal.critic.critique, {"n": 0}

    def interrupted(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise KeyboardInterrupt
        return real(*args, **kwargs)

    monkeypatch.setattr(cal.critic, "critique", interrupted)
    rows = [row(c, (5, 5, 5, 5)) for c in "abc"]
    code, llm, out = run(tmp_path, rows, [crit(), crit(), crit()])
    assert code == cal.EXIT_INCOMPLETE and len(llm.calls) == 1
    assert "Stopped early" in out and "KeyboardInterrupt" in out
    assert "| a | 5 / 5 / 5 / 5 | 5 / 5 / 5 / 5 |" in out and "- c: not attempted" in out


def test_a_trace_that_cannot_be_created_refuses_before_any_model_call(tmp_path, monkeypatch):
    def broken():
        raise trace.TraceWriteError("could not create trace: disk full")

    monkeypatch.setattr(trace, "start_run", broken)
    code, llm, out = run(tmp_path, [row("a", (5, 5, 5, 5))], [crit()])
    assert code == cal.EXIT_REFUSED and llm.calls == [] and "could not create trace" in out


def test_rows_without_your_scores_are_skipped_and_cost_no_request(tmp_path):
    rows = [row("a", (5, 5, 5, 5)), row("b"), row("c", (4, 4, 4, 4))]
    code, llm, out = run(tmp_path, rows, [crit(), crit()])
    assert code == cal.EXIT_OK and len(llm.calls) == 2  # skipped rows are not failures
    assert "1 drafts have no scores of yours and will be skipped" in out
    assert "1 skipped for having no scores of yours" in out and "| b | - | - | - | skipped: no hand scores |" in out
    assert "## Not scored" not in out
    code, llm, out = run(tmp_path, rows, [crit(), crit(), crit()], "--allow-unscored")
    assert code == cal.EXIT_OK and len(llm.calls) == 3 and "skipped for having" not in out


def test_check_says_how_many_rows_would_be_skipped(tmp_path):
    code, llm, out = run(tmp_path, [row("a", (5, 5, 5, 5)), row("b")], [], "--check")
    assert code == cal.EXIT_OK and llm.calls == [] and "1 drafts have no scores of yours" in out


def test_a_label_that_cannot_be_read_back_does_not_lose_the_scores(tmp_path, monkeypatch):
    def broken(run_id):
        raise ValueError("trace unreadable")

    monkeypatch.setattr(trace, "read_run", broken)
    code, _, out = run(tmp_path, [row("a", (5, 5, 5, 5))], [crit()])
    assert code == cal.EXIT_OK and "| a | 5 / 5 / 5 / 5 | 5 / 5 / 5 / 5 | pass / pass | - |" in out


# ---------- files saved by a spreadsheet, and output that cannot be shown or saved ----------

def test_comma_only_rows_left_by_excel_are_ignored(tmp_path):
    path = write_csv(tmp_path / "d.csv", [row("a", (5, 5, 5, 5)), row("b")])
    with path.open("a", encoding="utf-8", newline="") as f:
        f.write(",,,,,,,,\n,,,,,,,,\n")
    assert [r.draft_id for r in cal.read_rows(path, DAY)] == ["a", "b"]


def test_a_file_that_is_not_utf8_is_refused_with_the_fix(tmp_path):
    path = tmp_path / "d.csv"
    path.write_bytes("draft_id,text,my_voice,my_clarity,my_cta,my_policy\na,café bread,,,,\n".encode("cp1252"))
    with pytest.raises(cal.CalibrationError, match="CSV UTF-8"):
        cal.read_rows(path, DAY)
    out: list[str] = []
    assert cal.main(["--csv", str(path)], llm=MockLLM([]), now=NOW, say=out.append, env_file=None) == cal.EXIT_REFUSED
    assert any("CSV UTF-8" in line for line in out)


def test_a_semicolon_separated_file_gets_a_hint(tmp_path):
    path = tmp_path / "d.csv"
    path.write_text("draft_id;text;my_voice;my_clarity;my_cta;my_policy\na;hello;;;;\n", encoding="utf-8")
    with pytest.raises(cal.CalibrationError, match=r"comma-separated"):
        cal.read_rows(path, DAY)


def test_a_report_that_cannot_be_saved_is_still_printed(tmp_path):
    blocker = tmp_path / "afile"
    blocker.write_text("not a folder", encoding="utf-8")
    code, llm, out = run(tmp_path, [row("a", (5, 5, 5, 5))], [crit()], "--out", str(blocker / "report.md"))
    assert code == cal.EXIT_INCOMPLETE and len(llm.calls) == 1  # the requests were spent; the scores are not lost
    assert "# Critic calibration report" in out and "could not be saved" in out and "printed above" in out


def test_a_console_that_cannot_show_a_character_does_not_lose_the_report(tmp_path):
    text = "Une croûte dorée. https://example.com/bramblewick/classes"
    csv_path = write_csv(tmp_path / "d.csv", [row("a", (5, 5, 5, 5), text=text)])
    shown: list[str] = []

    def ascii_console(message: str) -> None:
        message.encode("ascii")  # what a cp1252 or cp437 pipe does with a character it cannot encode
        shown.append(message)

    code = cal.main(["--csv", str(csv_path), "--out", str(tmp_path / "r.md")], llm=MockLLM([crit(3, 3, 3, 3)]),
                    now=NOW, say=ascii_console, env_file=None)
    assert code == cal.EXIT_OK
    assert any("# Critic calibration report" in m and "cro?te" in m for m in shown)  # printed with a replacement
    assert "croûte" in (tmp_path / "r.md").read_text(encoding="utf-8")  # the saved file keeps the real text


# ---------- a good report is never lost, and the report says how the scores were made ----------

def test_a_failed_rerun_never_overwrites_the_report_of_a_complete_run(tmp_path):
    rows = [row(c, (5, 5, 5, 5)) for c in "abc"]
    code, _, _ = run(tmp_path, rows, [crit()] * 3)
    good = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert code == cal.EXIT_OK and "3 scored by the critic" in good and not list(tmp_path.glob("report.partial-*.md"))
    code, _, out = run(tmp_path, rows, [LLMUnavailable("all 3 models failed")])
    assert code == cal.EXIT_INCOMPLETE and "report.md was left as it was" in out
    assert (tmp_path / "report.md").read_text(encoding="utf-8") == good  # untouched
    [partial] = tmp_path.glob("report.partial-*.md")
    assert "0 scored by the critic" in partial.read_text(encoding="utf-8")


def test_a_complete_rerun_replaces_the_report(tmp_path):
    rows = [row("a", (5, 5, 5, 5))]
    run(tmp_path, rows, [crit(5, 5, 5, 5)])
    run(tmp_path, rows, [crit(3, 3, 3, 3)])
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "| a | 5 / 5 / 5 / 5 | 3 / 3 / 3 / 3 |" in report and not list(tmp_path.glob("report.partial-*.md"))


def test_the_report_discloses_adjusted_hand_scores_when_an_adjustments_note_sits_beside_the_csv(tmp_path):
    (tmp_path / "adjustments.md").write_text("six scores were changed", encoding="utf-8")
    _, _, out = run(tmp_path, [row("a", (5, 5, 5, 5))], [crit()])
    assert "**Note:** some of your hand scores were adjusted after review" in out
    assert "partly circular" in out and "drafts.first_pass.csv" in out


def test_without_an_adjustments_note_the_report_has_no_such_disclosure(tmp_path):
    _, _, out = run(tmp_path, [row("a", (5, 5, 5, 5))], [crit()])
    assert "adjusted after review" not in out and "**Note:**" not in out


# ---------- more ways a run can go wrong ----------

def test_an_unexpected_error_stops_the_run_and_keeps_the_scored_drafts(tmp_path, monkeypatch):
    real, calls = cal.critic.critique, {"n": 0}

    def buggy(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("something nobody planned for")
        return real(*args, **kwargs)

    monkeypatch.setattr(cal.critic, "critique", buggy)
    code, llm, out = run(tmp_path, [row(c, (5, 5, 5, 5)) for c in "abc"], [crit(), crit(), crit()])
    assert code == cal.EXIT_INCOMPLETE and len(llm.calls) == 1
    assert "unexpected RuntimeError: something nobody planned for" in out
    assert "| a | 5 / 5 / 5 / 5 | 5 / 5 / 5 / 5 |" in out and "- c: not attempted" in out


@pytest.mark.parametrize("value", ["0", "-3", "many"])
def test_max_requests_must_be_a_positive_whole_number(tmp_path, value):
    csv_path = write_csv(tmp_path / "d.csv", [row("a", (5, 5, 5, 5))])
    with pytest.raises(SystemExit) as stopped:
        cal.main(["--csv", str(csv_path), "--max-requests", value], llm=MockLLM([]), now=NOW,
                 say=lambda text: None, env_file=None)
    assert stopped.value.code == 2


def test_check_says_when_a_real_run_would_be_refused(tmp_path):
    code, llm, out = run(tmp_path, [row("a")], [], "--check")
    assert code == cal.EXIT_OK and llm.calls == [] and "note: a real run would be refused: no row has your scores" in out


def test_a_draft_id_with_a_pipe_does_not_break_the_tables(tmp_path):
    _, _, out = run(tmp_path, [row("a|b", (2, 2, 2, 2))], [crit(5, 5, 5, 5)])
    assert "| a\\|b |" in out and "| a|b |" not in out


def test_an_error_names_the_line_in_the_file_not_the_nth_record(tmp_path):
    path = tmp_path / "d.csv"
    path.write_text('draft_id,text,my_voice,my_clarity,my_cta,my_policy\n'
                    'a,"first line\nsecond line\nthird line",4,4,4,4\n'
                    'b,fine,9,4,4,4\n', encoding="utf-8")
    with pytest.raises(cal.CalibrationError, match=r"line 5: my_voice must be from 1 to 5"):
        cal.read_rows(path, DAY)


def test_a_field_over_the_csv_limit_is_a_clean_refusal(tmp_path):
    csv_path = write_csv(tmp_path / "d.csv", [row("a", (5, 5, 5, 5), text="x" * 200_000)])
    out: list[str] = []
    code = cal.main(["--csv", str(csv_path)], llm=MockLLM([]), now=NOW, say=out.append, env_file=None)
    assert code == cal.EXIT_REFUSED and any("could not be read as CSV" in line for line in out)


def test_a_refusal_that_quotes_a_non_ascii_value_does_not_crash_an_ascii_console(tmp_path):
    csv_path = write_csv(tmp_path / "d.csv", [row("a", ("五", "4", "4", "4"))])
    shown: list[str] = []

    def ascii_console(message: str) -> None:
        message.encode("ascii")
        shown.append(message)

    code = cal.main(["--csv", str(csv_path)], llm=MockLLM([]), now=NOW, say=ascii_console, env_file=None)
    assert code == cal.EXIT_REFUSED and any(m.startswith("refused: line 2: my_voice") for m in shown)


def test_an_env_file_that_cannot_be_read_is_refused_before_anything_runs(tmp_path):
    env_file = tmp_path / "bad.env"
    env_file.write_bytes("OPENROUTER_API_KEY=x\n".encode("utf-16"))  # what a PowerShell redirect can write
    csv_path = write_csv(tmp_path / "d.csv", [row("a", (5, 5, 5, 5))])
    llm, out = MockLLM([crit()]), []
    code = cal.main(["--csv", str(csv_path)], llm=llm, now=NOW, say=out.append, env_file=env_file)
    assert code == cal.EXIT_REFUSED and llm.calls == [] and any("bad.env could not be read" in line for line in out)
