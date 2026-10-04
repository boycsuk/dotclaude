#!/usr/bin/env python3
"""After an install, prove each central guard still blocks, run the way Claude Code runs it.

Usage: smoke-guards.py <settings.json> sh
       smoke-guards.py <settings.json> powershell <path to powershell.exe or pwsh>

The installers compile every hook before copying, but a guard can still be
silently off once installed: a mistyped command path, a Python the Windows
command no longer finds, or a launch form that turns exit 2 into 1. Each of
those fails open without a word. This feeds every guard one case it must
deny or ask, through the exact command string settings.json now holds, and
exits 1 naming each guard that let its case through.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid

# guard -> (tool_name, tool_input, the decision it must return)
CASES = {
    "guard-destructive": ("Bash", {"command": "rm -rf /"}, "deny"),
    "guard-push-main": ("Bash", {"command": "git push --force origin x"}, "deny"),
    "guard-commit": ("Bash", {"command": "git commit -s -m 'feat: x'"}, "deny"),
    "guard-dependencies": ("Bash", {"command": "npm install left-pad"}, "ask"),
    "guard-central-config": ("Edit", {"file_path": "~/.claude/settings.json",
                                      "old_string": "a", "new_string": "b"}, "deny"),
    # Judged, never run: the filesystem root is never under the temp folder
    # (a home can be, in a test install), so it is a write a read-only agent
    # may not make. Needs ~/.claude/agents/researcher.md, which the installer
    # copies before this runs.
    "guard-readonly-agents": ("Bash", {"command": "touch /dotclaude-smoke-probe"}, "deny"),
}
EXTRA = {"guard-readonly-agents": {"agent_id": "smoke", "agent_type": "researcher"}}
TIMEOUT = 30


def commands_for(settings, guard):
    """Every PreToolUse hook entry in `settings` that runs `guard` (its script in `command` or `args`)."""
    found = []
    for group in (settings.get("hooks") or {}).get("PreToolUse") or []:
        for hook in group.get("hooks") or []:
            command = hook.get("command")
            args = hook.get("args") if isinstance(hook.get("args"), list) else []
            if isinstance(command, str) and any(f"{guard}.py" in str(part) for part in [command] + args):
                found.append(hook)
    return found


def decision(stdout):
    try:
        out = json.loads(stdout.strip() or "{}")
    except ValueError:
        return None
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision")


def run(hook, payload, mode, shell_exe, cwd):
    """Run one hook entry the way Claude Code does: exec form when it has `args`, else through the shell."""
    command = hook["command"]
    if isinstance(hook.get("args"), list):
        argv = [command] + [str(a) for a in hook["args"]]
    elif mode == "powershell":
        argv = [shell_exe, "-NoProfile", "-NonInteractive", "-Command", command]
    else:
        argv = ["sh", "-c", command]
    try:
        proc = subprocess.run(argv, input=json.dumps(payload), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=TIMEOUT, cwd=cwd)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc)
    return decision(proc.stdout), f"exit {proc.returncode}: {proc.stderr.strip()[-200:]}"


def main():
    if len(sys.argv) < 3 or sys.argv[2] not in ("sh", "powershell") or \
            (sys.argv[2] == "powershell" and len(sys.argv) < 4):
        sys.stderr.write(__doc__)
        return 2
    path, mode = sys.argv[1], sys.argv[2]
    shell_exe = sys.argv[3] if mode == "powershell" else None
    with open(path, encoding="utf-8-sig") as fh:
        settings = json.load(fh)
    work = tempfile.mkdtemp(prefix="dotclaude-smoke-")
    problems = []
    try:
        for guard, (tool, tool_input, want) in CASES.items():
            commands = commands_for(settings, guard)
            if not commands:
                problems.append(f"{guard}: no PreToolUse entry runs it")
                continue
            payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input,
                       "cwd": work, "session_id": uuid.uuid4().hex, **EXTRA.get(guard, {})}
            for hook in commands:
                got, detail = run(hook, payload, mode, shell_exe, work)
                if got != want:
                    problems.append(f"{guard}: answered {got or 'nothing'} instead of {want} ({detail})")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if problems:
        sys.stderr.write("  ! smoke test: a guard did not block its test case, so it is off in every session:\n")
        for p in problems:
            sys.stderr.write(f"    - {p}\n")
        return 1
    print(f"  - smoke test: all {len(CASES)} guards block, run as Claude Code runs them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
