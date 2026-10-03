"""Run hooks the way Claude Code does, for the case matrices.

A `.py` hook has no `.sh`/`.ps1` twin, so there is no parity to check — but the
Windows *invocation* still differs: install.ps1 wires it as
`& "<python>" "<hook>.py"; exit $LASTEXITCODE` under PowerShell. With `pwsh`
given, `run` goes through that exact command form, so quoting, stdin or exit
code handling that breaks only under PowerShell fails the matrix instead of a
user's session. `ps1_hook` gives the same form for the `.ps1` twins.
"""

import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(REPO, "global/.claude/hooks")


def hook_path(name):
    return os.path.join(HOOKS, f"{name}.py")


def powershell_hook(pwsh, command):
    """argv that runs an install.ps1 hook `command` the way Claude Code does.

    A `"shell": "powershell"` hook is launched as `powershell -Command <command>`,
    and -Command turns a script's `exit 2` into process exit 1, which does not
    block. install.ps1 therefore appends `; exit $LASTEXITCODE`; running a
    matrix through `-File` instead hid that every .ps1 guard was non-blocking.
    """
    return [pwsh, "-NoProfile", "-NonInteractive", "-Command",
            f"{command}; exit $LASTEXITCODE"]


def home_env(path):
    """Environment that makes `path` the home directory for Python, PowerShell and git on any OS.

    Setting HOME alone isolates nothing on Windows: Python's expanduser reads
    USERPROFILE there and PowerShell's $HOME comes from USERPROFILE or
    HOMEDRIVE+HOMEPATH, so a test would read (or install into) the real profile.
    """
    drive, rest = os.path.splitdrive(path)
    return {"HOME": path, "USERPROFILE": path, "HOMEDRIVE": drive, "HOMEPATH": rest or path}


def ps_quote(text):
    """A PowerShell single-quoted literal: no `$` expansion, `'` doubled."""
    return "'" + text.replace("'", "''") + "'"


def ps1_hook(pwsh, script):
    """argv for a .ps1 hook, in the exact command form install.ps1 writes."""
    return powershell_hook(pwsh, f"& {ps_quote(script)}")


def argv(name, pwsh=None):
    """The argv that runs hook (or script) `name`, through PowerShell's production form if `pwsh`."""
    script = hook_path(name)
    if pwsh:
        return powershell_hook(pwsh, f"& {ps_quote(sys.executable)} {ps_quote(script)}")
    return [sys.executable, script]


def run(name, payload, cwd=None, env=None, pwsh=None):
    """Run hook `name` with `payload` on stdin; return (exit_code, parsed_stdout_or_None, stderr)."""
    cmd = argv(name, pwsh)
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
