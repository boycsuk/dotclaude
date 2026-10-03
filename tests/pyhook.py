"""Run a single-file Python hook the way Claude Code does, for the case matrices.

A `.py` hook has no `.sh`/`.ps1` twin, so there is no parity to check — but the
Windows *invocation* still differs: install.ps1 wires it as
`& "<python>" "<hook>.py"` under PowerShell. With `pwsh` given, `run` goes
through that exact command form, so quoting or stdin handling that breaks only
under PowerShell fails the matrix instead of a user's session.
"""

import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(REPO, "global/.claude/hooks")


def hook_path(name):
    return os.path.join(HOOKS, f"{name}.py")


def run(name, payload, cwd=None, env=None, pwsh=None):
    """Run hook `name` with `payload` on stdin; return (exit_code, parsed_stdout_or_None, stderr)."""
    script = hook_path(name)
    if pwsh:
        cmd = [pwsh, "-NoProfile", "-Command", f'& "{sys.executable}" "{script}"']
    else:
        cmd = [sys.executable, script]
    full_env = dict(os.environ, **(env or {}))
    if cwd:
        full_env.setdefault("CLAUDE_PROJECT_DIR", cwd)
    proc = subprocess.run(cmd, input=json.dumps(payload), capture_output=True,
                          text=True, encoding="utf-8", cwd=cwd, env=full_env)
    out = proc.stdout.strip()
    try:
        parsed = json.loads(out) if out else None
    except ValueError:
        parsed = {"_unparseable": out}
    return proc.returncode, parsed, proc.stderr


def decision(parsed):
    """The PreToolUse permissionDecision in a hook's output, or 'allow' when silent."""
    if not parsed:
        return "allow"
    return parsed.get("hookSpecificOutput", {}).get("permissionDecision", "allow")


def runners(pwsh):
    """The invocation forms to exercise: plain python, plus PowerShell if given."""
    return [("py", None)] + ([("ps", pwsh)] if pwsh else [])
