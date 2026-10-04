"""Run hooks the way Claude Code does, for the case matrices.

A `.py` hook has no `.sh`/`.ps1` twin, so there is no parity to check — but the
Windows *invocation* can differ. On Claude Code 2.1.139+ install.ps1 wires
exec form (python.exe spawned with the hook as its argument), which is what
the plain-python runner does. On an older or unknown version it falls back to
`& "<python>" "<hook>.py"; exit $LASTEXITCODE` under PowerShell; with `pwsh`
given, `run` goes through that exact command form, so quoting, stdin or exit
code handling that breaks only under PowerShell fails the matrix instead of a
user's session. `ps1_hook` gives the same form for the `.ps1` twins.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import uuid

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


def run(name, payload, cwd=None, env=None, pwsh=None, timeout=60):
    """Run hook `name` with `payload` on stdin; return (exit_code, parsed_stdout_or_None, stderr).

    A hook still running after `timeout` seconds returns exit code "TIMEOUT"
    instead of hanging the matrix (and CI) forever. `payload` may be a dict or
    an already-encoded string, for the malformed-input cases.
    """
    cmd = argv(name, pwsh)
    full_env = dict(os.environ, **(env or {}))
    if cwd:
        full_env.setdefault("CLAUDE_PROJECT_DIR", cwd)
    try:
        proc = subprocess.run(cmd, input=payload if isinstance(payload, str) else json.dumps(payload),
                              capture_output=True, text=True, encoding="utf-8", cwd=cwd, env=full_env,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return "TIMEOUT", None, ""
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


def reason(parsed):
    """The permissionDecisionReason in a hook's output, or ""."""
    return ((parsed or {}).get("hookSpecificOutput") or {}).get("permissionDecisionReason", "")


def context(parsed):
    """(additionalContext, hookEventName) in a hook's output; (None, None) when it has none."""
    specific = (parsed or {}).get("hookSpecificOutput") or {}
    return specific.get("additionalContext"), specific.get("hookEventName")


def verdict(code, parsed, err, feedback=False):
    """One crash rule for every matrix: the outcome of a hook run, or a "CRASH(...)" string.

    A guard or advisory hook must exit 0 with nothing on stderr (stderr at
    exit 0 is a traceback the debug log swallowed). A feedback hook may also
    exit 2, the channel that shows its stderr to Claude. Outcomes: "TIMEOUT";
    "feedback" or "quiet" for a feedback hook; otherwise the PreToolUse
    decision ("allow" when silent).
    """
    if code == "TIMEOUT":
        return "TIMEOUT"
    if feedback and code == 2:
        return "feedback"
    if code != 0 or err.strip():
        return f"CRASH(rc={code}, {err.strip()[-160:]!r})"
    return "quiet" if feedback else decision(parsed)


def payload(tool, tool_input, event="PreToolUse", **extra):
    """A hook payload shaped like production's: tool and event names, a fresh session id."""
    data = {"hook_event_name": event, "tool_name": tool, "tool_input": tool_input,
            "session_id": uuid.uuid4().hex}
    data.update(extra)
    return data


def edit_input(path, text, tool="Edit"):
    """The tool_input an Edit, Write or NotebookEdit of `path` with new text `text` sends."""
    if tool == "Write":
        return {"file_path": path, "content": text}
    if tool == "NotebookEdit":
        return {"notebook_path": path, "new_source": text}
    return {"file_path": path, "old_string": "", "new_string": text}


GIT_IDENTITY = ["-c", "user.name=matrix", "-c", "user.email=matrix@example.invalid"]


def git(repo, *args, check=True):
    """Run git in `repo` with a fixed identity; returns the CompletedProcess."""
    return subprocess.run(["git", "-C", repo] + GIT_IDENTITY + list(args), check=check,
                          capture_output=True, text=True)


def git_repo(branch="main", files=None, commit=True, prefix="matrix-repo-"):
    """A scratch git repository on `branch` holding `files` {path: text}, committed unless `commit` is False."""
    repo = tempfile.mkdtemp(prefix=prefix)
    subprocess.run(["git", "init", "-q", "-b", branch, repo], check=True, capture_output=True)
    for rel, text in (files or {}).items():
        path = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(path) or repo, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    if commit:
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "--allow-empty", "-m", "init")
    return repo


def local_settings(root, data):
    """Write `data` as root/.claude/settings.local.json, or remove the file when `data` is None."""
    path = os.path.join(root, ".claude", "settings.local.json")
    if data is None:
        if os.path.exists(path):
            os.remove(path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def cli(description=None):
    """The matrices' shared command line: --pwsh PATH runs every case through PowerShell too."""
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--pwsh", help="path to pwsh or powershell, to run through the PowerShell command form too")
    return ap.parse_args()


def finish(name, failures, total, pwsh=None, has_windows_form=True):
    """Print the standard last line (run-matrices.py shows it) and return the exit code.

    `has_windows_form` is False for a matrix with no PowerShell side, so its
    line does not suggest a --pwsh it does not take.
    """
    if failures:
        print(f"{name}: {failures} of {total} case(s) FAILED")
        return 1
    scope = ("" if not has_windows_form else
             " — python + powershell" if pwsh else " — python only (pass --pwsh for the Windows form)")
    print(f"{name}: {total} cases pass{scope}")
    return 0
