#!/usr/bin/env python3
"""Behavioural contract for hookio.entrypoint, the wrapper every hook exits through.

Run:  python3 tests/hook-entrypoint-cases.py
      python3 tests/hook-entrypoint-cases.py --pwsh PATH   # PowerShell command form too

An uncaught exception exits 1, which Claude Code treats as a non-blocking
error: a guard that crashed let the command run unjudged. Through the wrapper
a crashing guard asks the user instead, and any other hook kind exits 0 so a
crash in advice never interrupts the tool. Scratch hooks that raise on
purpose stand in for a real crash, run in the exact command forms production
uses.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyhook  # noqa: E402

HOOK = """# hook-kind: {kind}
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))
import hookio  # noqa: E402


def main():
    hookio.read_payload()
    {body}


if __name__ == "__main__":
    hookio.entrypoint(main)
"""

# (kind, main body, expected exit code, expected decision or None for silent stdout, why)
CASES = [
    ("guard", 'raise ValueError("embedded null byte")', 0, "ask", "a crashing guard asks instead of allowing"),
    ("guard", "return 0", 0, None, "a guard that decides nothing stays silent"),
    ("advisory", 'raise KeyError("x")', 0, None, "a crashing advisory hook exits 0 and says nothing"),
    ("feedback", "return 2", 2, None, "main's exit code passes through"),
    ("guard", "sys.exit(3)", 3, None, "an explicit sys.exit is not treated as a crash"),
]


def run(script, pwsh):
    if pwsh:
        cmd = pyhook.powershell_hook(pwsh, f"& {pyhook.ps_quote(sys.executable)} {pyhook.ps_quote(script)}")
    else:
        cmd = [sys.executable, script]
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}}
    proc = subprocess.run(cmd, input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8")
    out = proc.stdout.strip()
    return proc.returncode, (json.loads(out) if out else None), proc.stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh", help="path to pwsh, to run through the PowerShell command form too")
    args = ap.parse_args()

    work = tempfile.mkdtemp(prefix="hook-entrypoint-")
    failures = 0
    try:
        shutil.copytree(os.path.join(pyhook.HOOKS, "_lib"), os.path.join(work, "_lib"))
        for i, (kind, body, want_code, want_decision, why) in enumerate(CASES):
            script = os.path.join(work, f"case{i}.py")
            with open(script, "w", encoding="utf-8") as fh:
                fh.write(HOOK.format(kind=kind, body=body))
            for name, runner in pyhook.runners(args.pwsh):
                code, out, err = run(script, runner)
                got_decision = pyhook.decision(out) if out else None
                if code != want_code or got_decision != want_decision:
                    failures += 1
                    print(f"  FAIL [{name}] want exit {want_code}/{want_decision} got exit {code}/{got_decision}"
                          f" | {kind}: {body}   ({why}) {err.strip()[-160:]}")
                elif want_decision == "ask":
                    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
                    if "ValueError" not in reason or f"case{i}" not in reason:
                        failures += 1
                        print(f"  FAIL [{name}] the ask must name the hook and the error: {reason!r}")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    suffix = "" if args.pwsh else " — python only (pass --pwsh for the Windows form)"
    if failures:
        print(f"{failures} case(s) FAILED")
        return 1
    print(f"hook-entrypoint: {len(CASES)} cases pass{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
