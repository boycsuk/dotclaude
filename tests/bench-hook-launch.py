#!/usr/bin/env python3
"""Time one Bash call's guards under each way Claude Code can launch them.

Run:  python tests/bench-hook-launch.py [--runs N]

Measures the five Bash/PowerShell guards, started at once the way Claude Code
starts the hooks of one tool call, under:
  - exec form: python.exe spawned directly (install.ps1 on Claude Code 2.1.139+);
  - Windows PowerShell 5.1 and pwsh: `& 'python' 'hook'; exit $LASTEXITCODE`,
    the fallback form, when those shells are on PATH.
Prints the median wall time per form: what the launch form costs every tool
call. Not a matrix: it judges nothing, and it is run by hand on the machine
being measured.
"""

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HOOKS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "global", ".claude", "hooks")
GUARDS = ("guard-destructive", "guard-push-main", "guard-commit", "guard-dependencies", "guard-readonly-agents")
PAYLOAD = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "bench",
                      "tool_input": {"command": "ls"}, "cwd": os.getcwd()})


def ps_quote(text):
    return "'" + text.replace("'", "''") + "'"


def launchers():
    forms = [("exec form (python.exe directly)", lambda hook: [sys.executable, hook])]
    for name, label in (("powershell", "Windows PowerShell 5.1"), ("pwsh", "pwsh")):
        shell = shutil.which(name)
        if shell:
            forms.append((f"{label} (-Command ...; exit $LASTEXITCODE)",
                          lambda hook, shell=shell: [shell, "-NoProfile", "-NonInteractive", "-Command",
                                                     f"& {ps_quote(sys.executable)} {ps_quote(hook)}; exit $LASTEXITCODE"]))
    return forms


def one_call(argv_for):
    """Wall time of the five guards started together, as one tool call's hooks are."""
    def run(guard):
        subprocess.run(argv_for(os.path.join(HOOKS, f"{guard}.py")), input=PAYLOAD, capture_output=True, text=True)
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(GUARDS)) as pool:
        list(pool.map(run, GUARDS))
    return (time.perf_counter() - start) * 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=15)
    args = ap.parse_args()
    print(f"python: {sys.executable}")
    for label, argv_for in launchers():
        one_call(argv_for)                       # warm the disk cache
        times = [one_call(argv_for) for _ in range(args.runs)]
        print(f"  {label:<55} median {statistics.median(times):6.0f} ms per Bash call")
    return 0


if __name__ == "__main__":
    sys.exit(main())
