"""Calibrate the critic (D2-B): run the real critic on drafts you have scored by hand, and measure the gap.

    python -m evals.calibrate_critic --check      # validate the CSV and show the request plan; no model calls
    python -m evals.calibrate_critic              # score every draft, print and save data/calibration/report.md

Input is data/calibration/drafts.csv with draft_id, text and your own 1 to 5 scores (my_voice, my_clarity, my_cta,
my_policy). The optional topic, angle and goal columns give the critic the planned post it would see in a real run;
a blank falls back to the Saturday-class default. The critic itself is not changed, and `passed` is still computed
by the harness from the scores.

The run asks for temperature 0 where the model supports it (a model that rejects the field is skipped like any other
400), and a fallback to another model is recorded per draft: scores from several models are not one comparison.
Known limit: a model that rejects `temperature` answers 400 and is skipped, but it is asked again for the next draft
(a 400 can depend on the request), so such a model costs one extra request per draft; the request cap bounds it, and
the report names which model scored each draft.

It is capped by the daily request guard, so a flaky chain cannot drain the free quota. A row without your scores is
skipped (there is nothing to compare it with) unless --allow-unscored is given. The run stops, and still saves a
partial report, when the chain is unavailable, the key is refused, the trace cannot be written, or you press Ctrl+C:
the drafts already scored cost real requests and are not thrown away.

Exit codes: 0 every draft scored, 2 refused before any model call, 4 some drafts were not scored or the report could
not be saved (it is printed either way).
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
from harness.llm import LLM, LLMAuthError, LLMError, LLMUnavailable, OpenRouterLLM
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
# Asking again after one of these only repeats the failure (a refused key, a chain that is down, a trace that cannot
# be written) or is the user saying stop, so the run ends and keeps what it has.
STOP_RUN = (LLMUnavailable, LLMAuthError, trace.TraceWriteError, KeyboardInterrupt)


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
    skipped: bool = False  # left out on purpose (no hand scores), which is not a failure


def _blank(raw: dict) -> bool:
    """A row with nothing in any column. Excel leaves rows of bare commas after the data, and they are not mistakes."""
    return all(not (" ".join(v) if isinstance(v, list) else str(v or "")).strip() for v in raw.values())


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
    except UnicodeDecodeError:
        raise CalibrationError(f"{path.name} is not valid UTF-8; save it as 'CSV UTF-8' and try again") from None
    except OSError as e:
        raise CalibrationError(f"cannot read {path} ({type(e).__name__})") from None
    reader = csv.DictReader(io.StringIO(text))
    missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        hint = " (is the file comma-separated?)" if len(reader.fieldnames or []) <= 1 else ""
        raise CalibrationError(f"{path.name} is missing columns: {', '.join(missing)}{hint}")
    rows: list[Row] = []
    seen: set[str] = set()
    records: list[tuple[int, dict]] = []
    try:
        for raw in reader:
            records.append((reader.line_num, raw))  # the file line the record ended on, which is what a person looks for
    except csv.Error as e:  # e.g. one field larger than the csv module's limit
        raise CalibrationError(f"{path.name} could not be read as CSV ({e})") from None
    for line_number, raw in records:
        if _blank(raw):
            continue
        where = f"line {line_number}"
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
    try:
        answered = [e for e in trace.read_run(run_id) if e.agent == "critic" and e.kind == "llm_call" and e.ok]
    except (OSError, ValueError):
        return None  # only labels the report; a trace that cannot be read back must not lose the scores
    return answered[-1].model if answered else None


def score_rows(llm: LLM, rows: list[Row], brief: BrandBrief, *, min_score: int,
               max_requests: int) -> tuple[list[Scored], str | None, str, int]:
    """Returns (results, why scoring stopped early or None, the run id, requests used).

    A chain that is unavailable, a spent budget, a refused key, a trace that cannot be written or Ctrl+C stops the
    whole run (STOP_RUN): asking again for the next draft would only burn more of the free quota, and the drafts
    already scored are kept for the report. A reply that stays invalid after its repair fails that draft only.

    Each draft has the critic's own budget of 4 requests (decision 4.4): if one draft uses it all up, the chain is
    failing badly enough that asking again for the next draft would not recover, so the run stops there too.
    Any other unexpected error also stops the run and is named in the report, because by then requests are spent.
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
                continue
            except STOP_RUN as e:  # includes LLMBudgetExceeded
                stopped = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            except LLMError as e:
                item.error = f"{type(e).__name__}: {e}"
                continue
            except Exception as e:  # noqa: BLE001 - the scored drafts must survive a bug or an unexpected error type
                stopped = f"unexpected {type(e).__name__}: {e}"
            item.error = f"not scored: {stopped}"
            results.extend(Scored(r, error="not attempted: the run stopped earlier") for r in rows[index + 1:])
            break
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
                 stopped: str | None, generated: datetime, notes: Sequence[str] = ()) -> str:
    compared = [r for r in results if r.critique is not None and r.row.human is not None]
    scored = [r for r in results if r.critique is not None]
    models = sorted({r.model for r in scored if r.model})
    skipped = [r for r in results if r.skipped]
    lines = [
        "# Critic calibration report", "",
        f"- Generated: {generated.isoformat(timespec='seconds')}",
        f"- Run: `{run_id}` ({requests_used} upstream requests)",
        f"- Pass threshold: every score at least {min_score} (the harness's rule)",
        f"- Drafts: {len(results)} in the file, {len(scored)} scored by the critic, "
        f"{sum(r.row.human is not None for r in results)} with your scores, {len(compared)} compared"
        + (f", {len(skipped)} skipped for having no scores of yours" if skipped else ""),
        f"- Scored by: {', '.join(models) if models else 'no model answered'}",
    ]
    if len(models) > 1:
        lines.append("- **Warning:** more than one model answered, so these scores are not a single comparison; "
                     "rerun when one model is available for a cleaner result.")
    if stopped:
        lines.append(f"- **Stopped early:** {_cell(stopped)}")
    lines += [f"- **Note:** {_cell(n)}" for n in notes]
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
                  + (f" ({', '.join(_cell(r.row.draft_id) for r in lenient)})" if lenient else ""),
                  f"- Critic fails a draft you would pass (too strict): {len(strict)}"
                  + (f" ({', '.join(_cell(r.row.draft_id) for r in strict)})" if strict else ""), ""]

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
                lines.append(f"| {_cell(r.row.draft_id)} | {_cell(r.row.text, 80)} | {_scores(r.row.human)} "  # type: ignore[arg-type]
                             f"| {_scores(r.critique)} | {_cell(reasons)} |")  # type: ignore[arg-type]
            lines.append("")

    lines += ["## Every draft", "", "| Draft | You | Critic | Pass (you / critic) | Scored by |", "|---|---|---|---|---|"]
    for r in results:
        if r.critique is None:
            lines.append(f"| {_cell(r.row.draft_id)} | {_scores(r.row.human) if r.row.human else '-'} | - | - | {_cell(r.error or '-')} |")
            continue
        mine_pass = "-" if r.row.human is None else ("pass" if _human_passes(r.row.human, min_score) else "fail")
        lines.append(f"| {_cell(r.row.draft_id)} | {_scores(r.row.human) if r.row.human else '-'} | {_scores(r.critique)} "
                     f"| {mine_pass} / {'pass' if r.critique.passed else 'fail'} | {_cell(r.model or '-')} |")
    failures = [r for r in results if r.critique is None and r.error and not r.skipped]
    if failures:
        lines += ["", "## Not scored", ""] + [f"- {_cell(r.row.draft_id)}: {_cell(r.error or '')}" for r in failures]
    return "\n".join(lines) + "\n"


def _at_least_one(value: str) -> int:
    n = int(value)  # argparse turns a ValueError into a clean usage error
    if n < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return n


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="calibrate_critic", description=__doc__.split("\n")[0])
    p.add_argument("--csv", default=str(DEFAULT_CSV), help="the hand-scored drafts (default: data/calibration/drafts.csv)")
    p.add_argument("--out", default=str(DEFAULT_REPORT), help="where to save the report")
    p.add_argument("--min-score", type=int, choices=range(1, 6), default=4, metavar="1-5")
    p.add_argument("--max-requests", type=_at_least_one, default=None,
                   help=f"model requests this run may make (default {DEFAULT_MAX_REQUESTS}; never more than the daily guard allows)")
    p.add_argument("--check", action="store_true", help="validate the CSV and show the plan, with no model calls")
    p.add_argument("--allow-unscored", action="store_true",
                   help="run even if no row has your scores yet (spends requests on a report with nothing to compare)")
    return p.parse_args(argv)


def _say_safe(say: Callable[[str], None], text: str) -> None:
    try:
        say(text)
    except UnicodeEncodeError:
        say(text.encode("ascii", "replace").decode("ascii"))


def main(argv: Sequence[str] | None = None, *, llm: LLM | None = None, now: datetime | None = None,
         say: Callable[[str], None] = print, env_file: Path | None = DEFAULT_ENV_FILE) -> int:
    """Tests inject `llm` and `now` and pass env_file=None so the real .env never loads."""
    args = parse_args(argv)
    # Every message goes through the console-safe printer: a refusal that quotes a bad value (a score typed in
    # another script, say) must not itself crash on a console that cannot show it.
    emit, say = say, (lambda text: _say_safe(emit, text))
    if env_file is not None:
        try:
            load_dotenv(env_file)
        except (OSError, UnicodeDecodeError) as e:  # e.g. a .env saved as UTF-16 by a shell redirect
            say(f"refused: {env_file.name} could not be read ({type(e).__name__}); save it as UTF-8")
            return EXIT_REFUSED
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
    # A row without your scores has nothing to be compared with, so by default it costs no request.
    targets = rows if args.allow_unscored else [r for r in rows if r.human is not None]
    used, unreadable = quota.llm_calls_since(now - quota.WINDOW)
    remaining = max(0, quota.DAILY_REQUEST_LIMIT - used)
    max_requests = min(DEFAULT_MAX_REQUESTS if args.max_requests is None else args.max_requests, remaining)
    note = f" ({unreadable} unreadable traces, so the count may be low)" if unreadable else ""
    say(f"{len(rows)} drafts, {hand} with your scores; threshold {args.min_score}; this run may make up to "
        f"{max_requests} requests ({used} used in the last 24 hours{note})")
    if len(targets) < len(rows):
        say(f"{len(rows) - len(targets)} drafts have no scores of yours and will be skipped "
            "(pass --allow-unscored to score them anyway)")
    refusal = None
    if hand == 0 and not args.allow_unscored:
        refusal = "no row has your scores yet. Fill in the my_* columns, or pass --allow-unscored."
    elif max_requests <= 0:
        refusal = "the daily request guard has no requests left; try again when older requests age out"
    if args.check:
        say("check only: no model calls made")
        if refusal:
            say(f"note: a real run would be refused: {refusal}")
        return EXIT_OK
    if refusal:
        say(f"refused: {refusal}")
        return EXIT_REFUSED
    if max_requests < len(targets):
        say(f"warning: only {max_requests} requests are available for {len(targets)} drafts, so some will not be scored")

    try:
        llm = llm or OpenRouterLLM(temperature=0.0)
    except LLMError as e:
        say(f"refused: {e}")
        return EXIT_REFUSED
    try:
        results, stopped, run_id, requests_used = score_rows(llm, targets, brief, min_score=args.min_score,
                                                             max_requests=max_requests)
    except trace.TraceWriteError as e:  # the trace could not even be created, so no request was made
        say(f"refused: {e}")
        return EXIT_REFUSED
    by_id = {s.row.draft_id: s for s in results}
    ordered = [by_id.get(r.draft_id) or Scored(r, error="skipped: no hand scores", skipped=True) for r in rows]
    # Hand scores changed after review (data/calibration/adjustments.md) must be disclosed by any report built on them.
    adjustments = Path(args.csv).with_name("adjustments.md")
    notes = [f"some of your hand scores were adjusted after review, so this is not purely your own judgment: see "
             f"{adjustments.name} (your first-pass scores are kept in drafts.first_pass.csv). The review used the "
             "critic's own rubric, so the comparison is partly circular."] if adjustments.exists() else []
    report = build_report(ordered, min_score=args.min_score, requests_used=requests_used, run_id=run_id,
                          stopped=stopped, generated=now, notes=notes)
    complete = all(r.critique is not None for r in ordered if not r.skipped)
    # Printed first and whatever happens next: the requests are spent, so the report must not be lost to a full
    # disk or a console that cannot show a character in a draft.
    say(report)
    out = Path(args.out)
    # Only a complete run replaces the report. A partial one is saved beside it, so a rerun that fails early
    # (the chain down, a refused key) can never overwrite the good report from an earlier run.
    target = out if complete else out.with_name(f"{out.stem}.partial-{run_id}{out.suffix}")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(report, encoding="utf-8", newline="\n")
    except OSError as e:
        say(f"warning: the report could not be saved to {target} ({type(e).__name__}); it is printed above")
        saved = False
    else:
        say(f"saved {target}" + ("" if complete else f" (incomplete, so {out.name} was left as it was)"))
        saved = True
    return EXIT_OK if complete and saved else EXIT_INCOMPLETE


if __name__ == "__main__":
    sys.exit(main())
