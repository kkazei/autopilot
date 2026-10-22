"""Deterministic brand-safety checks that stand between a passing critique and publish_post.

Each check is a pure function returning {"ok": bool, "reasons": list[str]}, so every block
comes with a reason a human can read in the trace. run_all is the only function with side
effects: it logs every decision as a guardrail event and asks for approval last.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any, TypedDict

from harness import trace
from harness.schemas import MAX_POST_CHARS

RATE_WINDOW = timedelta(hours=24)
DEFAULT_DUPLICATE_THRESHOLD = 0.9
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"))
_NON_WORD = re.compile(r"[^\w]+")


class CheckResult(TypedDict):
    ok: bool
    reasons: list[str]


def _result(reasons: list[str]) -> CheckResult:
    return {"ok": not reasons, "reasons": reasons}


def _normalize(text: str) -> str:
    """Fold case, width tricks, zero-width characters and punctuation so "B.e.s.t" or "ＢＥＳＴ" cannot dodge a match."""
    text = unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH).casefold()
    return " ".join(_NON_WORD.sub(" ", text).replace("_", " ").split())


def check_length(text: str, max: int = MAX_POST_CHARS) -> CheckResult:  # noqa: A002 - name is from the plan's contract
    """Counts code points; Bluesky counts graphemes, so this is slightly stricter for emoji, never looser."""
    if not text.strip():
        return _result(["post is empty"])
    if len(text) > max:
        return _result([f"post is {len(text)} characters; the limit is {max}"])
    return _result([])


def check_banned(text: str, brief: Mapping[str, Any]) -> CheckResult:
    """Whole-word match on normalized text. A brief without a usable list fails closed instead of passing everything."""
    phrases = brief.get("banned_phrases")
    if not isinstance(phrases, list) or not all(isinstance(p, str) for p in phrases):
        return _result(["brand brief has no valid banned_phrases list"])
    haystack = f" {_normalize(text)} "
    hits = [p for p in phrases if _normalize(p) and f" {_normalize(p)} " in haystack]
    return _result([f"contains banned phrase: {p!r}" for p in hits])


def _parse_ts(value: Any) -> datetime:
    ts = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if ts.tzinfo is None:
        raise ValueError("naive timestamp")
    return ts


def check_rate_cap(
    now: datetime,
    published_log: Iterable[Mapping[str, Any]],
    max_per_day: int = 3,
    min_gap_minutes: int = 60,
) -> CheckResult:
    """"A day" is a rolling 24 hours, so posting cannot burst across midnight. Exactly 60 minutes since the last post passes.

    An unreadable publish record fails closed: if we cannot tell when we last posted, we do not post.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    try:
        times = [_parse_ts(r["posted_at"]) for r in published_log]
    except (KeyError, TypeError, ValueError):
        return _result(["publish log has an unreadable posted_at; refusing to post"])
    reasons: list[str] = []
    in_window = [t for t in times if t > now - RATE_WINDOW]
    if len(in_window) >= max_per_day:
        reasons.append(f"rate cap: {len(in_window)} posts in the last 24 hours (max {max_per_day})")
    if times:
        gap = now - max(times)
        if gap < timedelta(minutes=min_gap_minutes):
            minutes = int(gap.total_seconds() // 60)
            reasons.append(f"last post was {minutes} minutes ago; minimum gap is {min_gap_minutes}")
    return _result(reasons)


def check_duplicate(
    text: str, recent_texts: Iterable[str], threshold: float = DEFAULT_DUPLICATE_THRESHOLD
) -> CheckResult:
    """Similarity on normalized text, so a repost with new punctuation or casing still counts as a repeat."""
    if not 0 < threshold <= 1:
        raise ValueError("threshold must be in (0, 1]")
    candidate = _normalize(text)
    for recent in recent_texts:
        ratio = SequenceMatcher(None, candidate, _normalize(recent)).ratio()
        if ratio >= threshold:
            return _result([f"near-duplicate of a recent post (similarity {ratio:.2f} >= {threshold:.2f})"])
    return _result([])


def require_approval(text: str, enabled: bool, *, input_fn: Callable[[str], str] = input) -> CheckResult:
    """Only an explicit "y" or "yes" approves; anything else, including closed stdin, means no."""
    if not enabled:
        return _result([])
    prompt = f"\n--- draft ({len(text)} chars) ---\n{text}\n--- end ---\nPublish this post? [y/N] "
    try:
        answer = input_fn(prompt)
    except EOFError:
        return _result(["no approval input (stdin closed)"])
    if answer.strip().lower() in ("y", "yes"):
        return _result([])
    return _result(["human reviewer did not approve"])


def run_all(
    text: str,
    brief: Mapping[str, Any],
    *,
    run_id: str,
    now: datetime,
    published_log: Iterable[Mapping[str, Any]],
    recent_texts: Iterable[str],
    approval_enabled: bool,
    input_fn: Callable[[str], str] = input,
    max_len: int = MAX_POST_CHARS,
    max_per_day: int = 3,
    min_gap_minutes: int = 60,
    duplicate_threshold: float = DEFAULT_DUPLICATE_THRESHOLD,
) -> dict[str, Any]:
    """Run every deterministic check (all of them, so the trace lists every reason), then ask a human only if they all passed.

    Asking last means a reviewer is never shown a draft the harness would block anyway.
    """
    checks: dict[str, CheckResult] = {
        "check_length": check_length(text, max_len),
        "check_banned": check_banned(text, brief),
        "check_rate_cap": check_rate_cap(now, published_log, max_per_day, min_gap_minutes),
        "check_duplicate": check_duplicate(text, recent_texts, duplicate_threshold),
    }
    for name, result in checks.items():
        _log(run_id, name, text, result)

    if all(r["ok"] for r in checks.values()):
        checks["require_approval"] = require_approval(text, approval_enabled, input_fn=input_fn)
    else:
        checks["require_approval"] = _result(["skipped: deterministic checks failed"])
    approval_note = None if approval_enabled else "pass (approval disabled)"
    _log(run_id, "require_approval", text, checks["require_approval"], approval_note)

    reasons = [f"{name}: {reason}" for name, r in checks.items() for reason in r["reasons"]]
    return {"ok": not reasons, "reasons": reasons, "checks": checks}


def _log(run_id: str, name: str, text: str, result: CheckResult, pass_note: str | None = None) -> None:
    summary_out = (pass_note or "pass") if result["ok"] else "; ".join(result["reasons"])
    trace.log_event(run_id, "harness", "guardrail", f"{name} | {text}", summary_out, ok=result["ok"])
