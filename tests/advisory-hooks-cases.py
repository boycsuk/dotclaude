#!/usr/bin/env python3
"""Behavioural contract for the four ADVISORY hooks.

Run:  python3 tests/advisory-hooks-cases.py
      python3 tests/advisory-hooks-cases.py --pwsh PATH   # verify parity

Covers reinject-rules, sync-mirror-docs, prefer-serena-bash and prefer-graphify
— the hooks check.py's matrix requirement silently exempted, and the only ones
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
    hook "warning" there reaches nobody (§27a). reinject-rules is the one
    exception: SessionStart adds plain-text stdout to context directly.
  - silence when there is nothing to say, so the nudges stay credible. A hook
    that fires on every call is noise, and noise teaches the model to ignore
    it (the cry-wolf failure DESIGN.md §26 warns about).
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(REPO, "global/.claude/hooks")

NUDGE, SILENT = "NUDGE", "SILENT"


def run(runner, hook, payload, cwd, env_extra=None):
    """Pipe real hook JSON through the script; return (verdict, stdout, rc)."""
    script = os.path.join(HOOKS, hook + (".ps1" if runner == "ps1" else ".sh"))
    cmd = ([PWSH, "-NoProfile", "-File", script] if runner == "ps1"
           else ["bash", script])
    env = dict(os.environ, CLAUDE_PROJECT_DIR=cwd)
    # Each case gets its own HOME so the 5-minute debounce marker of one case
    # cannot silence the next one.
    env["HOME"] = tempfile.mkdtemp()
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(cmd, input=json.dumps(payload), capture_output=True,
                          text=True, cwd=cwd, env=env, timeout=30)
    return proc


def delivered_context(stdout):
    """The additionalContext string if stdout carries the documented shape."""
    for line in stdout.strip().splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except ValueError:
            continue
        specific = data.get("hookSpecificOutput") or {}
        ctx = specific.get("additionalContext")
        if ctx:
            return ctx, specific.get("hookEventName")
    return None, None


def check(label, cond, detail=""):
    global failures
    if cond:
        print(f"  ok  {label}")
    else:
        failures += 1
        print(f"  FAIL {label}{(' | ' + detail) if detail else ''}")


def case_reinject(runner):
    """SessionStart: plain stdout IS the channel here, so assert content."""
    cwd = tempfile.mkdtemp()
    proc = run(runner, "reinject-rules", {"source": "compact"}, cwd)
    check(f"[{runner}] reinject-rules exits 0", proc.returncode == 0,
          f"rc={proc.returncode}")
    out = proc.stdout
    check(f"[{runner}] reinject-rules emits the digest on stdout",
          "POST-COMPACTION REMINDER" in out, repr(out[:120]))
    # The digest's whole purpose is rules enforced ONLY by prose. If it starts
    # restating deterministic guarantees it will grow without bound.
    check(f"[{runner}] digest covers the amend/trailer/branch rules",
          all(k in out for k in ("--amend", "Co-Authored-By", "CHANGELOG.md")),
          "a non-negotiable convention went missing from the digest")


def case_sync_mirror(runner):
    """PostToolUse: fires on rule edits only, via additionalContext."""
    cwd = tempfile.mkdtemp()

    edited = os.path.join(cwd, "global/.claude/rules/workflow.md")
    proc = run(runner, "sync-mirror-docs",
               {"tool_name": "Edit", "tool_input": {"file_path": edited}}, cwd)
    ctx, event = delivered_context(proc.stdout)
    check(f"[{runner}] sync-mirror-docs exits 0 on a rule edit",
          proc.returncode == 0, f"rc={proc.returncode}")
    check(f"[{runner}] rule edit delivers additionalContext", ctx is not None,
          f"stdout={proc.stdout[:160]!r} stderr={proc.stderr[:160]!r}")
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
    ctx, _ = delivered_context(proc.stdout)
    check(f"[{runner}] a non-rule edit stays silent", ctx is None, repr(ctx))
    check(f"[{runner}] silent path still exits 0", proc.returncode == 0,
          f"rc={proc.returncode}")

    ai = os.path.join(cwd, ".claude/rules/ai-collaboration.md")
    proc = run(runner, "sync-mirror-docs",
               {"tool_name": "Edit", "tool_input": {"file_path": ai}}, cwd)
    ctx, _ = delivered_context(proc.stdout)
    check(f"[{runner}] ai-collaboration.md names the output style",
          bool(ctx) and "output-styles" in ctx, repr(ctx))


def case_prefer_serena(runner):
    """PreToolUse on Bash: nudge only when the command reads a code file."""
    cwd = tempfile.mkdtemp()
    os.makedirs(os.path.join(cwd, ".serena"), exist_ok=True)

    proc = run(runner, "prefer-serena-bash",
               {"tool_name": "Bash",
                "tool_input": {"command": "grep -n foo src/app.ts"}}, cwd)
    check(f"[{runner}] prefer-serena-bash never blocks", proc.returncode == 0,
          f"rc={proc.returncode}")
    ctx, event = delivered_context(proc.stdout)
    check(f"[{runner}] grep over a code file nudges", ctx is not None,
          f"stdout={proc.stdout[:160]!r} stderr={proc.stderr[:160]!r}")
    check(f"[{runner}] hookEventName is PreToolUse", event == "PreToolUse",
          repr(event))

    proc = run(runner, "prefer-serena-bash",
               {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}, cwd)
    ctx, _ = delivered_context(proc.stdout)
    check(f"[{runner}] a non-reading command stays silent", ctx is None,
          repr(ctx))


def case_prefer_graphify(runner):
    """PreToolUse: gated on a built graph, so silent where none exists."""
    cwd = tempfile.mkdtemp()
    payload = {"tool_name": "Bash",
               "tool_input": {"command": "grep -rn handler src/app.py"}}

    proc = run(runner, "prefer-graphify", payload, cwd)
    ctx, _ = delivered_context(proc.stdout)
    check(f"[{runner}] prefer-graphify silent without a graph", ctx is None,
          repr(ctx))
    check(f"[{runner}] and still exits 0", proc.returncode == 0,
          f"rc={proc.returncode}")

    # The gate is graphify-out/graph.json; without this the careful nudge logic
    # behind it would never see a single interesting input.
    out = os.path.join(cwd, "graphify-out")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "graph.json"), "w") as fh:
        json.dump({"nodes": []}, fh)

    proc = run(runner, "prefer-graphify", payload, cwd)
    ctx, event = delivered_context(proc.stdout)
    check(f"[{runner}] nudges once a graph exists", ctx is not None,
          f"stdout={proc.stdout[:160]!r} stderr={proc.stderr[:160]!r}")
    check(f"[{runner}] points at graphify query",
          bool(ctx) and "graphify" in ctx.lower(), repr(ctx))
    check(f"[{runner}] hookEventName is PreToolUse", event == "PreToolUse",
          repr(event))
    check(f"[{runner}] nudging never blocks", proc.returncode == 0,
          f"rc={proc.returncode}")


def main():
    global failures, PWSH
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh", help="path to pwsh, to verify .ps1 parity")
    args = ap.parse_args()
    PWSH = args.pwsh
    failures = 0

    runners = ["sh"] + (["ps1"] if args.pwsh else [])
    for runner in runners:
        print(f"\n=== {runner}")
        case_reinject(runner)
        case_sync_mirror(runner)
        case_prefer_serena(runner)
        case_prefer_graphify(runner)

    scope = "bash + powershell" if args.pwsh else "bash only (pass --pwsh for parity)"
    print(f"\nadvisory-hooks: {failures} bad — {scope}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
