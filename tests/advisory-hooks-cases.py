#!/usr/bin/env python3
"""Behavioural contract for the advisory hooks reinject-rules.py and sync-mirror-docs.py.

Run:  python3 tests/advisory-hooks-cases.py
      python3 tests/advisory-hooks-cases.py --pwsh PATH   # also through PowerShell

Covers reinject-rules and sync-mirror-docs (prefer-serena-bash and prefer-graphify
were removed with Serena and Graphify, DESIGN.md §33) — the hooks check.py's matrix requirement silently exempted, and the only ones
whose failure mode is SILENCE. A guard hook that breaks is noticed within
seconds (it blocks everything). An advisory hook that breaks is indistinguish-
able from one with nothing to say, which is exactly how three of them sat on a
dead channel (stderr + exit 0) for months before DESIGN.md §17 caught it.

So these cases assert the DELIVERY CONTRACT, not merely that something was
printed:

  - exit 0 always. An advisory hook must never gate the tool call: editing a
    rule, grepping, or reading a file are all legitimate.
  - the nudge arrives on STDOUT as hookSpecificOutput.additionalContext, with
    the right hookEventName. stderr at exit 0 goes to the debug log only, so a
    hook "warning" there reaches nobody (§27a).
  - silence when there is nothing to say, so the nudges stay credible. A hook
    that fires on every call is noise, and noise teaches the model to ignore
    it (the cry-wolf failure DESIGN.md §26 warns about).
"""

import argparse
import atexit
import os
import shutil
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyhook  # noqa: E402


def scratch():
    path = tempfile.mkdtemp()
    atexit.register(shutil.rmtree, path, True)
    return path


def run(runner, hook, payload, cwd):
    """Run the hook as production does; return an object with returncode, out (parsed) and stderr."""
    code, out, err = pyhook.run(hook, payload, cwd=cwd, pwsh=PWSH if runner == "ps1" else None,
                                env=pyhook.home_env(scratch()))
    return SimpleNamespace(returncode=code, out=out, stderr=err)


def delivered_context(out):
    """The additionalContext string and event if the output carries the documented shape."""
    specific = (out or {}).get("hookSpecificOutput") or {}
    ctx = specific.get("additionalContext")
    return (ctx, specific.get("hookEventName")) if ctx else (None, None)


def check(label, cond, detail=""):
    global failures
    if cond:
        print(f"  ok  {label}")
    else:
        failures += 1
        print(f"  FAIL {label}{(' | ' + detail) if detail else ''}")


def case_reinject(runner):
    """SessionStart: the digest arrives as additionalContext."""
    cwd = scratch()
    proc = run(runner, "reinject-rules", {"hook_event_name": "SessionStart", "source": "compact"}, cwd)
    check(f"[{runner}] reinject-rules exits 0", proc.returncode == 0,
          f"rc={proc.returncode}")
    out, event = delivered_context(proc.out)
    out = out or ""
    check(f"[{runner}] reinject-rules delivers the digest as SessionStart context",
          "POST-COMPACTION REMINDER" in out and event == "SessionStart", repr(proc.out)[:160])
    # The digest's whole purpose is rules enforced ONLY by prose. If it starts
    # restating deterministic guarantees it will grow without bound.
    check(f"[{runner}] digest covers the prose-only workflow rules",
          all(k in out for k in ("branch", "CHANGELOG.md", "AskUserQuestion")),
          "a non-negotiable convention went missing from the digest")
    # --amend and attribution trailers are enforced by guard-commit since
    # DESIGN.md §36, so restating them here is the unbounded growth above.
    check(f"[{runner}] digest leaves hook-enforced rules to the hooks",
          not any(k in out for k in ("--amend", "Co-Authored-By")),
          "the digest restates a rule guard-commit already enforces")


def case_sync_mirror(runner):
    """PostToolUse: fires on rule edits only, via additionalContext."""
    cwd = scratch()

    edited = os.path.join(cwd, "global/.claude/rules/workflow.md")
    proc = run(runner, "sync-mirror-docs",
               {"tool_name": "Edit", "tool_input": {"file_path": edited}}, cwd)
    ctx, event = delivered_context(proc.out)
    check(f"[{runner}] sync-mirror-docs exits 0 on a rule edit",
          proc.returncode == 0, f"rc={proc.returncode}")
    check(f"[{runner}] rule edit delivers additionalContext", ctx is not None,
          f"out={proc.out!r} stderr={proc.stderr[:160]!r}")
    check(f"[{runner}] names the conventions mirror",
          bool(ctx) and "conventions.md" in ctx, repr(ctx))
    check(f"[{runner}] hookEventName is PostToolUse", event == "PostToolUse",
          repr(event))
    # workflow.md feeds the post-compaction digest; that obligation is the one
    # most easily forgotten because nothing breaks when it is missed.
    check(f"[{runner}] workflow.md edit also names reinject-rules",
          bool(ctx) and "reinject-rules" in ctx, repr(ctx))

    other = os.path.join(cwd, "src/main.py")
    proc = run(runner, "sync-mirror-docs",
               {"tool_name": "Edit", "tool_input": {"file_path": other}}, cwd)
    ctx, _ = delivered_context(proc.out)
    check(f"[{runner}] a non-rule edit stays silent", ctx is None, repr(ctx))
    check(f"[{runner}] silent path still exits 0", proc.returncode == 0,
          f"rc={proc.returncode}")

    ai = os.path.join(cwd, ".claude/rules/ai-collaboration.md")
    proc = run(runner, "sync-mirror-docs",
               {"tool_name": "Edit", "tool_input": {"file_path": ai}}, cwd)
    ctx, _ = delivered_context(proc.out)
    check(f"[{runner}] ai-collaboration.md names the output style",
          bool(ctx) and "output-styles" in ctx, repr(ctx))
    # ai-collaboration also feeds the digest; dropping that arm passed before.
    check(f"[{runner}] ai-collaboration.md also names reinject-rules",
          bool(ctx) and "reinject-rules" in ctx, repr(ctx))
    security = os.path.join(cwd, ".claude/rules/security.md")
    proc = run(runner, "sync-mirror-docs",
               {"tool_name": "Edit", "tool_input": {"file_path": security}}, cwd)
    ctx, _ = delivered_context(proc.out)
    check(f"[{runner}] security.md names the mirror but not the digest",
          bool(ctx) and "conventions.md" in ctx and "reinject-rules" not in ctx, repr(ctx))


def main():
    global failures, PWSH
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh", help="path to pwsh, to run through the PowerShell command form too")
    args = ap.parse_args()
    PWSH = args.pwsh
    failures = 0

    runners = ["py"] + (["ps1"] if args.pwsh else [])
    for runner in runners:
        print(f"\n=== {runner}")
        case_reinject(runner)
        case_sync_mirror(runner)

    scope = "python + powershell" if args.pwsh else "python only (pass --pwsh for the Windows form)"
    print(f"\nadvisory-hooks: {failures} bad — {scope}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
