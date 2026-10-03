#!/usr/bin/env python3
"""Behavioural contract for statusline.{sh,ps1}.

Run:  python3 tests/statusline-cases.py
      python3 tests/statusline-cases.py --pwsh PATH   # verify parity

A status line runs on every assistant message, after /compact, and on
permission-mode changes. Two invariants matter more than what it prints:

  1. It must ALWAYS exit 0 and write nothing to stderr. Whatever it emits lands
     where the status belongs, so a traceback or a `command not found` becomes
     permanent visual noise in the interface.
  2. It must print NOTHING when it has nothing true to say. `used_percentage`
     is null before the first API call and again right after /compact, and a
     status line that renders that as `0% ctx` lies at exactly the moment
     someone looks at it to decide whether to commit.

Both are invisible to a test that only checks the happy path.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SH = os.path.join(REPO, "global/.claude/hooks/statusline.sh")
PS1 = os.path.join(REPO, "global/.claude/hooks/statusline.ps1")


def run(payload, pwsh=None, cwd=None):
    cmd = [pwsh, "-NoProfile", "-File", PS1] if pwsh else ["bash", SH]
    p = subprocess.run(cmd, input=payload, capture_output=True, text=True,
                       cwd=cwd or REPO)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def check(payload, pwsh, why, must_contain=None, must_not_contain=None,
          expect_empty=False):
    rc, out, err = run(payload, pwsh)
    if rc != 0:
        return f"{why}: exited {rc} — a status line must always exit 0"
    if err:
        return f"{why}: wrote to stderr ({err[:80]}) — it would show in the bar"
    if expect_empty:
        return None if not out else f"{why}: printed {out!r} when it should stay silent"
    if not out:
        return f"{why}: printed nothing"
    if "\n" in out:
        return f"{why}: printed multiple lines — {out!r}"
    for needle in (must_contain or []):
        if needle not in out:
            return f"{why}: missing {needle!r} — got {out!r}"
    for needle in (must_not_contain or []):
        if needle in out:
            return f"{why}: contains {needle!r} — got {out!r}"
    return None


def p(**kw):
    return json.dumps(kw)


def ctx(pct, size=200000):
    return {"used_percentage": pct, "context_window_size": size}


def case_model_and_context(_, pwsh):
    return check(p(model={"display_name": "Opus"}, context_window=ctx(8)),
                 pwsh, "model + context", must_contain=["Opus", "8% ctx"])


def case_high_context_warns(_, pwsh):
    return check(p(model={"display_name": "Opus"}, context_window=ctx(75)),
                 pwsh, "75% of a 200k window", must_contain=["!75% ctx"])


def case_low_pct_but_low_headroom(_, pwsh):
    """A 100k window at 65% has 35k left — below the 40k headroom floor — while
    the 70% rule alone would stay quiet. (The old case, a 1M window at 97%, was
    already caught by the 70% rule, so deleting the headroom clause passed.)"""
    return check(p(model={"display_name": "Opus"}, context_window=ctx(65, 100000)),
                 pwsh, "small window, low headroom", must_contain=["!65% ctx"])


def case_fraction_truncates_on_both_shells(_, pwsh):
    """69.6% is not yet 70%: the .ps1 rounded with [int] and warned alone."""
    return check(p(model={"display_name": "Opus"}, context_window=ctx(69.6)),
                 pwsh, "69.6% of a 200k window", must_contain=["69% ctx"], must_not_contain=["!"])


def case_large_window_early_no_warn(_, pwsh):
    return check(p(model={"display_name": "Opus"}, context_window=ctx(8, 1000000)),
                 pwsh, "1M window early", must_not_contain=["!"])


def case_null_percentage(_, pwsh):
    """Null right after /compact: print the model, never a fabricated 0%."""
    return check(p(model={"display_name": "Opus"},
                   context_window={"used_percentage": None}),
                 pwsh, "null used_percentage",
                 must_contain=["Opus"], must_not_contain=["%"])


def case_missing_context_window(_, pwsh):
    return check(p(model={"display_name": "Opus"}),
                 pwsh, "no context_window at all",
                 must_contain=["Opus"], must_not_contain=["%"])


def case_context_only(_, pwsh):
    return check(p(context_window=ctx(50)), pwsh, "no model",
                 must_contain=["50% ctx"])


def case_empty_object(_, pwsh):
    return check("{}", pwsh, "empty payload", expect_empty=True)


def case_garbage(_, pwsh):
    return check("not json at all", pwsh, "garbage stdin", expect_empty=True)


def case_empty_stdin(_, pwsh):
    return check("", pwsh, "empty stdin", expect_empty=True)


def case_unexpected_types(_, pwsh):
    """A schema change must not produce a traceback in the status bar."""
    return check(json.dumps({"model": "a bare string",
                             "context_window": "also a string"}),
                 pwsh, "wrong types throughout", expect_empty=True)


CASES = [
    ("model and context render", case_model_and_context),
    ("high context warns", case_high_context_warns),
    ("low headroom warns below 70%", case_low_pct_but_low_headroom),
    ("a fraction truncates the same on both shells", case_fraction_truncates_on_both_shells),
    ("large window early does not warn", case_large_window_early_no_warn),
    ("null percentage prints no percentage", case_null_percentage),
    ("missing context_window degrades", case_missing_context_window),
    ("context without model renders", case_context_only),
    ("empty payload stays silent", case_empty_object),
    ("garbage stdin stays silent", case_garbage),
    ("empty stdin stays silent", case_empty_stdin),
    ("unexpected field types stay silent", case_unexpected_types),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh", help="path to pwsh, to verify the .ps1 too")
    args = ap.parse_args()

    targets = [(None, "sh")]
    if args.pwsh:
        targets.append((args.pwsh, "ps1"))

    total = bad = 0
    for pwsh, label in targets:
        for name, fn in CASES:
            tmp = tempfile.mkdtemp(prefix="statusline-case-")
            try:
                problem = fn(tmp, pwsh)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            total += 1
            if problem:
                bad += 1
            status = "ok  " if problem is None else "BAD "
            print(f"  {status}[{label}] {name}" + (f" — {problem}" if problem else ""))

    suffix = "" if args.pwsh else " — bash only (pass --pwsh for parity)"
    print(f"\nstatusline: {total - bad} ok, {bad} bad{suffix}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
