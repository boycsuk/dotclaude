#!/usr/bin/env python3
"""Behavioural contract for scripts/smoke-guards.py, the installers' post-install check.

Run:  python3 tests/smoke-guards-cases.py

The smoke test is only worth running if it fails when a guard is off. Each
case writes a settings.json whose guard commands point at this repo's hooks,
then breaks one of them the way an install can: a wrong path, a missing
entry. The real install path, under both installers, is exercised by
tests/install-cases.py.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyhook  # noqa: E402

SMOKE = os.path.join(pyhook.REPO, "scripts", "smoke-guards.py")
GUARDS = ("guard-destructive", "guard-push-main", "guard-commit", "guard-dependencies", "guard-central-config")


# Windows has no `sh`; there the installers wire hooks in PowerShell's form.
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh") if os.name == "nt" else None


def command(script):
    if POWERSHELL:
        return f"& {pyhook.ps_quote(sys.executable)} {pyhook.ps_quote(script)}; exit $LASTEXITCODE"
    return f'"{sys.executable}" "{script}"'


def settings(hooks_dir, drop=None, break_path=None):
    entries = []
    for guard in GUARDS:
        if guard == drop:
            continue
        script = os.path.join(hooks_dir, ("missing-" if guard == break_path else "") + f"{guard}.py")
        entries.append({"type": "command", "command": command(script), "timeout": 20})
    return {"hooks": {"PreToolUse": [{"matcher": "Bash|PowerShell|Edit|Write", "hooks": entries}]}}


def smoke(home, data):
    path = os.path.join(home, "settings.json")
    with open(path, "w") as fh:
        json.dump(data, fh)
    mode = ["powershell", POWERSHELL] if POWERSHELL else ["sh"]
    return subprocess.run([sys.executable, SMOKE, path] + mode, capture_output=True, text=True,
                          env=dict(os.environ, **pyhook.home_env(home)))


def main():
    home = tempfile.mkdtemp(prefix="smoke-guards-")
    failures = 0
    try:
        os.makedirs(os.path.join(home, ".claude"))
        with open(os.path.join(home, ".claude", "settings.json"), "w") as fh:
            fh.write("{}")
        cases = [
            ("every guard wired and working", settings(pyhook.HOOKS), 0, None),
            ("a guard whose script path is wrong", settings(pyhook.HOOKS, break_path="guard-push-main"),
             1, "guard-push-main"),
            ("a guard no entry runs", settings(pyhook.HOOKS, drop="guard-commit"), 1, "guard-commit"),
        ]
        for label, data, want, must_name in cases:
            proc = smoke(home, data)
            if proc.returncode != want or (must_name and must_name not in proc.stderr):
                failures += 1
                print(f"  FAIL {label}: exit {proc.returncode}, stderr {proc.stderr.strip()[-300:]!r}")
    finally:
        shutil.rmtree(home, ignore_errors=True)
    if failures:
        print(f"{failures} case(s) FAILED")
        return 1
    print("smoke-guards: 3 cases pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
