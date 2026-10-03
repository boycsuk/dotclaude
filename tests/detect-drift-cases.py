#!/usr/bin/env python3
"""Behavioural contract for skills/init-project/scripts/detect-drift.py.

Run:  python3 tests/detect-drift-cases.py

The skill reads this script's KEY=VALUE lines to decide what to offer in
--update mode and to verify the §8 choices landed. It promises never to raise
and to answer UNKNOWN for a file it cannot read — before these cases a
`null` hook event crashed it, a BOM-prefixed file (Notepad, PowerShell 5.1)
read as clean, and a corrupt settings.local.json read as ABSENT. Each case
runs the script the way the skill does: from the project root, with the
template found through TEMPLATE_DIR.
"""

import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "skills/init-project/scripts/detect-drift.py")
TEMPLATE_DIR = os.path.join(REPO, "templates/project")

LEGACY_SETTINGS = ('{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": ['
                   '{"type": "command", "command": "\\"$HOME\\"/.claude/hooks/prefer-graphify.sh"}]}]}}')


def write(project, rel, text, bom=False):
    path = os.path.join(project, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig" if bom else "utf-8") as fh:
        fh.write(text)


def legacy_project(project, bom=False):
    write(project, ".claude/settings.json", LEGACY_SETTINGS, bom)
    write(project, ".claude/settings.local.json", '{"allowPushToMain": true}', bom)
    write(project, ".mcp.json", '{"mcpServers": {"serena": {"command": "serena"}}}', bom)
    os.makedirs(os.path.join(project, ".serena"))


def run(project, path_prefix=None):
    env = dict(os.environ, TEMPLATE_DIR=TEMPLATE_DIR)
    if path_prefix:
        env["PATH"] = path_prefix + os.pathsep + env["PATH"]
    proc = subprocess.run([sys.executable, SCRIPT], cwd=project, env=env,
                          capture_output=True, text=True)
    values = dict(line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line)
    return proc.returncode, values, proc.stderr


LEGACY = {"OBSOLETE_HOOKS": "1", "OBSOLETE_MCP": "serena",
          "OBSOLETE_FILES": ".serena", "ALLOW_PUSH_MAIN": "TRUE"}


def case_legacy(project):
    legacy_project(project)
    return run(project), LEGACY


def case_bom(project):
    legacy_project(project, bom=True)
    return run(project), LEGACY


def case_serena_installed(project):
    # dotclaude no longer keeps Serena's hooks for users who still have it.
    write(project, ".claude/settings.json",
          '{"hooks": {"SessionStart": [{"hooks": [{"type": "command", '
          '"command": "serena-hooks activate --client=claude-code"}]}]}}')
    stub = os.path.join(project, "bin")
    os.makedirs(stub)
    with open(os.path.join(stub, "serena-hooks"), "w") as fh:
        fh.write("#!/bin/sh\nexit 0\n")
    os.chmod(os.path.join(stub, "serena-hooks"), 0o755)
    return run(project, stub), {"OBSOLETE_HOOKS": "1"}


def case_null_event(project):
    write(project, ".claude/settings.json", '{"hooks": {"PreToolUse": null}}')
    return run(project), {"OBSOLETE_HOOKS": "0", "ALLOW_PUSH_MAIN": "ABSENT"}


def case_corrupt(project):
    write(project, ".claude/settings.json", "{not json")
    write(project, ".claude/settings.local.json", "{not json")
    return run(project), {"OBSOLETE_HOOKS": "UNKNOWN", "ALLOW_PUSH_MAIN": "UNKNOWN"}


def case_list_local(project):
    write(project, ".claude/settings.local.json", "[]")
    return run(project), {"ALLOW_PUSH_MAIN": "UNKNOWN"}


def case_clean(project):
    write(project, ".claude/settings.local.json", '{"allowPushToMain": false}')
    return run(project), {"OBSOLETE_HOOKS": "0", "OBSOLETE_MCP": "",
                          "OBSOLETE_FILES": "", "ALLOW_PUSH_MAIN": "FALSE"}


CASES = [
    ("a legacy project reports every leftover", case_legacy),
    ("BOM-prefixed files read the same as plain ones", case_bom),
    ("Serena's hooks count as obsolete even with serena-hooks installed", case_serena_installed),
    ("a null hook event does not crash it", case_null_event),
    ("unreadable files report UNKNOWN, never clean or ABSENT", case_corrupt),
    ("a non-object settings.local.json reports UNKNOWN", case_list_local),
    ("a clean project reports nothing", case_clean),
]


def main():
    bad = 0
    for name, fn in CASES:
        project = tempfile.mkdtemp(prefix="drift-case-")
        try:
            (code, values, err), want = fn(project)
        finally:
            shutil.rmtree(project, ignore_errors=True)
        problem = None
        if code != 0 or err.strip():
            problem = f"exit {code}, stderr {err.strip()[-200:]!r}; it must never fail"
        else:
            wrong = {k: values.get(k) for k, v in want.items() if values.get(k) != v}
            if wrong:
                problem = f"got {wrong}, want {dict((k, want[k]) for k in wrong)}"
        bad += bool(problem)
        print(f"  {'ok  ' if not problem else 'BAD '}{name}" + (f" — {problem}" if problem else ""))
    print(f"\ndetect-drift: {len(CASES) - bad} ok, {bad} bad")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
