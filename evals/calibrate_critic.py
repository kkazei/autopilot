"""Calibrate the critic (D2-B): run the real critic on drafts you have scored by hand, and measure the gap.

    python -m evals.calibrate_critic --check      # validate the CSV and show the request plan; no model calls
    python -m evals.calibrate_critic              # score every draft, print and save data/calibration/report.md

Input is data/calibration/drafts.csv with draft_id, text and your own 1 to 5 scores (my_voice, my_clarity, my_cta,
my_policy). The optional topic, angle and goal columns give the critic the planned post it would see in a real run;
a blank falls back to the Saturday-class default. The critic itself is not changed, and `passed` is still computed
by the harness from the scores.

The run asks for temperature 0 where the model supports it (a model that rejects the field is skipped like any other
400), and a fallback to another model is recorded per draft: scores from several models are not one comparison.
It is capped by the daily request guard, so a flaky chain cannot drain the free quota.

Exit codes: 0 every draft scored, 2 refused before any model call, 4 some drafts were not scored.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from agents import critic
from agents.base import run_budget
from harness import quota, trace
from harness.env import load_dotenv
from harness.llm import LLM, LLMError, LLMUnavailable, OpenRouterLLM
from harness.schemas import CRITIQUE_DIMENSIONS, BrandBrief, Critique, Draft, PlannedPost, passes_threshold

EXIT_OK, EXIT_REFUSED, EXIT_INCOMPLETE = 0, 2, 4
CALIBRATION_DIR = trace.REPO_ROOT / "data" / "calibration"
DEFAULT_CSV = CALIBRATION_DIR / "drafts.csv"
DEFAULT_REPORT = CALIBRATION_DIR / "report.md"
DEFAULT_ENV_FILE = trace.REPO_ROOT / ".env"
HUMAN_COLUMNS = {"voice": "my_voice", "clarity": "my_clarity", "cta": "my_cta", "policy_risk": "my_policy"}
REQUIRED_COLUMNS = ("draft_id", "text", *HUMAN_COLUMNS.values())
DEFAULT_PLAN = {"topic": "Saturday beginner sourdough class",
                "angle": "one concrete detail a beginner would notice", "goal": "click"}
# One critic call per draft, a few more for fallbacks; well under the daily 50, and never above what is left today.
DEFAULT_MAX_REQUESTS = 24
TOP_DISAGREEMENTS = 3


class CalibrationError(ValueError):
    """The CSV or the setup is wrong; nothing is sent to a model."""


@dataclass(frozen=True)
class Row:
    draft_id: str
    text: str
    human: dict[str, int] | None  # None while the row has no hand scores yet
    planned: PlannedPost


@dataclass
class Scored:
    row: Row
    critique: Critique | None = None
    model: str | None = None
    error: str | None = None


def _score(value: str | None, column: str, where: str) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        n = int(value)
    except ValueError:
        raise CalibrationError(f"{where}: {column} must be a whole number from 1 to 5, not {value!r}") from None
    if not 1 <= n <= 5:
        raise CalibrationError(f"{where}: {column} must be from 1 to 5, not {n}")
    return n


def read_rows(path: Path, day: date) -> list[Row]:
    """Every row is validated up front, so a typo in row 9 does not surface after eight rows of quota are spent."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as e:
        raise CalibrationError(f"cannot read {path} ({type(e).__name__})") from None
    reader = csv.DictReader(io.StringIO(text))
    missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise CalibrationError(f"{path.name} is missing columns: {', '.join(missing)}")
    rows: list[Row] = []
    seen: set[str] = set()
    for number, raw in enumerate(reader, start=2):
        where = f"row {number}"
        draft_id = (raw.get("draft_id") or "").strip()
        if not draft_id:
            raise CalibrationError(f"{where}: draft_id is empty")
        if draft_id in seen:
            raise CalibrationError(f"{where}: draft_id {draft_id!r} appears twice")
        seen.add(draft_id)
        scores = {dim: _score(raw.get(column), column, where) for dim, column in HUMAN_COLUMNS.items()}
        filled = [v for v in scores.values() if v is not None]
        if filled and len(filled) != len(scores):
            raise CalibrationError(f"{where}: fill in all four of {', '.join(HUMAN_COLUMNS.values())}, or none")
        text_value = raw.get("text") or ""
        try:
            Draft(post_id=draft_id, text=text_value, attempt=1)
            plan = {k: (raw.get(k) or "").strip() or v for k, v in DEFAULT_PLAN.items()}
            planned = PlannedPost(id=f"cal_{draft_id}", day=day, **plan)
        except ValidationError as e:
            problem = e.errors()[0]
            raise CalibrationError(f"{where}: {'.'.join(map(str, problem['loc']))}: {problem['msg']}") from None
        if not text_value.strip():
            raise CalibrationError(f"{where}: text is empty")
        rows.append(Row(draft_id, text_value, scores if filled else None, planned))  # type: ignore[arg-type]
    if not rows:
        raise CalibrationError(f"{path.name} has no rows")
    return rows


def _model_of(run_id: str) -> str | None:
    """The model that answered the critic's last call, from the trace (a fallback may have changed it)."""
    answered = [e for e in trace.read_run(run_id) if e.agent == "critic" and e.kind == "llm_call" and e.ok]
    return answered[-1].model if answered else None


def score_rows(llm: LLM, rows: list[Row], brief: BrandBrief, *, min_score: int,
               max_requests: int) -> tuple[list[Scored], str | None, str, int]:
    """Returns (results, why scoring stopped early or None, the run id, requests used).

    A chain that is unavailable or a spent budget stops the whole run: asking again for the next draft
    would only burn more of the free quota. A reply that stays invalid after its repair fails that draft only.
    """
    run_id = trace.start_run()
    results: list[Scored] = []
    stopped: str | None = None
    with run_budget(max_requests) as budget:
        for index, row in enumerate(rows):
            item = Scored(row)
            results.append(item)
            try:
                draft = Draft(post_id=row.draft_id, text=row.text, attempt=1)
                item.critique = critic.critique(llm, run_id, draft, row.planned, brief, min_score)
                item.model = _model_of(run_id)
            except LLMUnavailable as e:  # includes LLMBudgetExceeded
                stopped = f"{type(e).__name__}: {e}"
                item.error = f"not scored: {stopped}"
                results.extend(Scored(r, error="not attempted: the run stopped earlier") for r in rows[index + 1:])
                break
            except LLMError as e:
                item.error = f"{type(e).__name__}: {e}"
        used = budget.used
    return results, stopped, run_id, used


def _cell(text: str, limit: int | None = None) -> str:
    text = " ".join(str(text).split()).replace("|", "\\|")
    return text if limit is None or len(text) <= limit else text[: limit - 1] + "…"


def _scores(values: dict[str, int] | Critique) -> str:
    get = values.get if isinstance(values, dict) else lambda d: getattr(values, d)
    return " / ".join(str(get(d)) for d in CRITIQUE_DIMENSIONS)


def _human_passes(human: dict[str, int], min_score: int) -> bool:
    return all(human[d] >= min_score for d in CRITIQUE_DIMENSIONS)


def build_report(results: list[Scored], *, min_score: int, requests_used: int, run_id: str,
                 stopped: str | None, generated: datetime) -> str:
    compared = [r for r in results if r.critique is not None and r.row.human is not None]
    scored = [r for r in results if r.critique is not None]
    models = sorted({r.model for r in scored if r.model})
    lines = [
        "# Critic calibration report", "",
        f"- Generated: {generated.isoformat(timespec='seconds')}",
        f"- Run: `{run_id}` ({requests_used} upstream requests)",
        f"- Pass threshold: every score at least {min_score} (the harness's rule)",
        f"- Drafts: {len(results)} in the file, {len(scored)} scored by the critic, "
        f"{sum(r.row.human is not None for r in results)} with your scores, {len(compared)} compared",
        f"- Scored by: {', '.join(models) if models else 'no model answered'}",
    ]
    if len(models) > 1:
        lines.append("- **Warning:** more than one model answered, so these scores are not a single comparison; "
                     "rerun when one model is available for a cleaner result.")
    if stopped:
        lines.append(f"- **Stopped early:** {_cell(stopped)}")
    lines.append("")

    if not compared:
        lines += ["## Result", "", "No draft has both your scores and a critic score yet, so there is nothing to compare. "
                  "Fill in the `my_*` columns of `drafts.csv` and run again.", ""]
    else:
        lines += ["## Mean absolute error per dimension", "",
                  "| Dimension | Mean absolute error | Critic minus you (bias) |", "|---|---|---|"]
        for dim in CRITIQUE_DIMENSIONS:
            diffs = [getattr(r.critique, dim) - r.row.human[dim] for r in compared]  # type: ignore[index, union-attr]
            lines.append(f"| {dim} | {sum(abs(d) for d in diffs) / len(diffs):.2f} | {sum(diffs) / len(diffs):+.2f} |")
        mine = {r.row.draft_id: _human_passes(r.row.human, min_score) for r in compared}  # type: ignore[arg-type]
        agree = sum(r.critique.passed == mine[r.row.draft_id] for r in compared)  # type: ignore[union-attr]
        lenient = [r for r in compared if r.critique.passed and not mine[r.row.draft_id]]  # type: ignore[union-attr]
        strict = [r for r in compared if not r.critique.passed and mine[r.row.draft_id]]  # type: ignore[union-attr]
        lines += ["", "## Pass or fail agreement", "",
                  f"- Agreement: **{agree} of {len(compared)}** ({agree / len(compared):.0%})",
                  f"- Critic passes a draft you would fail (too lenient): {len(lenient)}"
                  + (f" ({', '.join(r.row.draft_id for r in lenient)})" if lenient else ""),
                  f"- Critic fails a draft you would pass (too strict): {len(strict)}"
                  + (f" ({', '.join(r.row.draft_id for r in strict)})" if strict else ""), ""]

        def gap(r: Scored) -> int:
            return sum(abs(getattr(r.critique, d) - r.row.human[d]) for d in CRITIQUE_DIMENSIONS)  # type: ignore[index, arg-type]

        worst = sorted((r for r in compared if gap(r) > 0), key=lambda r: (-gap(r), r.row.draft_id))[:TOP_DISAGREEMENTS]
        lines += [f"## The {TOP_DISAGREEMENTS} biggest disagreements", ""]
        if not worst:
            lines += ["None: the critic matched your score on every dimension of every draft.", ""]
        else:
            lines += ["Scores are voice / clarity / cta / policy_risk.", "",
                      "| Draft | Text | You | Critic | Critic's reasons where you differ |", "|---|---|---|---|---|"]
            for r in worst:
                differing = [d for d in CRITIQUE_DIMENSIONS if getattr(r.critique, d) != r.row.human[d]]  # type: ignore[index]
                reasons = "; ".join(f"**{d}**: {r.critique.reasons.get(d, '')}" for d in differing)  # type: ignore[union-attr]
                lines.append(f"| {r.row.draft_id} | {_cell(r.row.text, 80)} | {_scores(r.row.human)} "  # type: ignore[arg-type]
                             f"| {_scores(r.critique)} | {_cell(reasons)} |")  # type: ignore[arg-type]
            lines.append("")

    lines += ["## Every draft", "", "| Draft | You | Critic | Pass (you / critic) | Scored by |", "|---|---|---|---|---|"]
    for r in results:
        if r.critique is None:
            lines.append(f"| {r.row.draft_id} | {_scores(r.row.human) if r.row.human else '-'} | - | - | {_cell(r.error or '-')} |")
            continue
        mine_pass = "-" if r.row.human is None else ("pass" if _human_passes(r.row.human, min_score) else "fail")
        lines.append(f"| {r.row.draft_id} | {_scores(r.row.human) if r.row.human else '-'} | {_scores(r.critique)} "
                     f"| {mine_pass} / {'pass' if r.critique.passed else 'fail'} | {_cell(r.model or '-')} |")
    failures = [r for r in results if r.critique is None and r.error]
    if failures:
        lines += ["", "## Not scored", ""] + [f"- {r.row.draft_id}: {_cell(r.error or '')}" for r in failures]
    return "\n".join(lines) + "\n"


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="calibrate_critic", description=__doc__.split("\n")[0])
    p.add_argument("--csv", default=str(DEFAULT_CSV), help="the hand-scored drafts (default: data/calibration/drafts.csv)")
    p.add_argument("--out", default=str(DEFAULT_REPORT), help="where to save the report")
    p.add_argument("--min-score", type=int, choices=range(1, 6), default=4, metavar="1-5")
    p.add_argument("--max-requests", type=int, default=None,
                   help=f"model requests this run may make (default {DEFAULT_MAX_REQUESTS}; never more than the daily guard allows)")
    p.add_argument("--check", action="store_true", help="validate the CSV and show the plan, with no model calls")
    p.add_argument("--allow-unscored", action="store_true",
                   help="run even if no row has your scores yet (spends requests on a report with nothing to compare)")
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None, *, llm: LLM | None = None, now: datetime | None = None,
         say: Callable[[str], None] = print, env_file: Path | None = DEFAULT_ENV_FILE) -> int:
    """Tests inject `llm` and `now` and pass env_file=None so the real .env never loads."""
    args = parse_args(argv)
    if env_file is not None:
        load_dotenv(env_file)
    now = now or datetime.now(timezone.utc)
    try:
        rows = read_rows(Path(args.csv), now.date())
        brief = BrandBrief.model_validate_json((trace.data_dir() / "brand_brief.json").read_text(encoding="utf-8"))
    except CalibrationError as e:
        say(f"refused: {e}")
        return EXIT_REFUSED
    except OSError as e:
        say(f"refused: brand brief could not be read ({type(e).__name__})")
        return EXIT_REFUSED
    except ValidationError as e:
        say(f"refused: brand brief is invalid ({e.error_count()} errors)")
        return EXIT_REFUSED

    hand = sum(r.human is not None for r in rows)
    used, unreadable = quota.llm_calls_since(now - quota.WINDOW)
    remaining = max(0, quota.DAILY_REQUEST_LIMIT - used)
    max_requests = min(args.max_requests or DEFAULT_MAX_REQUESTS, remaining)
    note = f" ({unreadable} unreadable traces, so the count may be low)" if unreadable else ""
    say(f"{len(rows)} drafts, {hand} with your scores; threshold {args.min_score}; this run may make up to "
        f"{max_requests} requests ({used} used in the last 24 hours{note})")
    if args.check:
        say("check only: no model calls made")
        return EXIT_OK
    if hand == 0 and not args.allow_unscored:
        say("refused: no row has your scores yet. Fill in the my_* columns, or pass --allow-unscored.")
        return EXIT_REFUSED
    if max_requests <= 0:
        say("refused: the daily request guard has no requests left; try again when older requests age out")
        return EXIT_REFUSED
    if max_requests < len(rows):
        say(f"warning: only {max_requests} requests are available for {len(rows)} drafts, so some will not be scored")

    try:
        llm = llm or OpenRouterLLM(temperature=0.0)
    except LLMError as e:
        say(f"refused: {e}")
        return EXIT_REFUSED
    results, stopped, run_id, requests_used = score_rows(llm, rows, brief, min_score=args.min_score,
                                                         max_requests=max_requests)
    report = build_report(results, min_score=args.min_score, requests_used=requests_used, run_id=run_id,
                          stopped=stopped, generated=now)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8", newline="\n")
    say(report)
    say(f"saved {out}")
    return EXIT_OK if all(r.critique is not None for r in results) else EXIT_INCOMPLETE


if __name__ == "__main__":
    sys.exit(main())
