#!/usr/bin/env python3
"""Behavioural contract for global/.claude/skills/init-project/scripts/detect-drift.py.

Run:  python3 tests/detect-drift-cases.py

The skill reads this script's KEY=VALUE lines to decide what to offer in
--update mode and to verify the deploy choices landed. It promises never to raise
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyhook  # noqa: E402
import stubs  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "global/.claude/skills/init-project/scripts/detect-drift.py")
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
                          capture_output=True, encoding="utf-8", errors="replace")
    values = dict(line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line)
    return proc.returncode, values, proc.stderr


LEGACY = {"OBSOLETE_HOOKS": "1", "OBSOLETE_MCP": "serena",
          "OBSOLETE_FILES": ".serena", "ALLOW_PUSH_MAIN": "TRUE", "MCP_SERVERS": "serena"}


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
    stubs.write_stub(stub, "serena-hooks")
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
    return run(project), {"OBSOLETE_HOOKS": "0", "OBSOLETE_MCP": "", "OBSOLETE_FILES": "",
                          "ALLOW_PUSH_MAIN": "FALSE", "MCP_SERVERS": "", "SETTINGS_EXAMPLE_DRIFT": "ABSENT",
                          "LEGACY_DESIGN_DOCS": ""}


def case_legacy_ui_md(project):
    # docs/ui.md left the template; /implement-ui migrates it into docs/design/.
    write(project, "docs/ui.md", "# UI\n")
    return run(project), {"LEGACY_DESIGN_DOCS": "docs/ui.md"}


def case_design_folder_is_not_legacy(project):
    # A migration that wrote docs/design/ but kept the old file is still unfinished,
    # while the specs in docs/design/ are the destination, never a candidate.
    write(project, "docs/ui.md", "# UI\n")
    write(project, "docs/design/README.md", "# Design\n")
    write(project, "docs/design/components/ui-button/README.md", "# Button\n")
    return run(project), {"LEGACY_DESIGN_DOCS": "docs/ui.md"}


def case_design_named_docs_anywhere(project):
    # Any Markdown file whose name reads as design, wherever it sits, minus
    # dependencies, build output and files whose name says nothing about design.
    write(project, "STYLEGUIDE.md", "# Style\n")
    write(project, "design-system.md", "# Tokens\n")
    write(project, "app/docs/screens.md", "# Screens\n")
    write(project, "docs/backend.md", "# API\n")
    write(project, "node_modules/lib/ui.md", "# not ours\n")
    write(project, "build/theme.md", "# generated\n")
    write(project, "docs/guide.txt", "ui\n")
    return run(project), {"LEGACY_DESIGN_DOCS": "STYLEGUIDE.md,app/docs/screens.md,design-system.md"}


def case_design_named_folder(project):
    # A whole design folder (prestashop has design/ with 66 Spanish-named specs)
    # is one candidate; a code folder that merely shares a name is none.
    write(project, "design/01-cabecera/01-1-barra.md", "# Barra\n")
    write(project, "design/index.html", "<p></p>\n")
    write(project, "src/components/Button.tsx", "export {}\n")
    return run(project), {"LEGACY_DESIGN_DOCS": "design/"}


def case_unreadable_subdirectory(project):
    # A root-owned Docker volume in the tree must not turn the answer into UNKNOWN.
    write(project, "docs/ui.md", "# UI\n")
    locked = os.path.join(project, "data", "locked")
    os.makedirs(locked)
    os.chmod(locked, 0)
    try:
        return run(project), {"LEGACY_DESIGN_DOCS": "docs/ui.md"}
    finally:
        os.chmod(locked, 0o755)


def case_example_drift(project):
    # The deploy prints DRIFT on the user's terminal, which the skill never
    # sees, so the skill reads it here. The copy is written with CRLF: line
    # endings alone (a Windows checkout) are no edit.
    with open(os.path.join(TEMPLATE_DIR, ".claude", "settings.local.json.example"), encoding="utf-8", newline="") as fh:
        crlf = fh.read().replace("\r\n", "\n").replace("\n", "\r\n")
    path = os.path.join(project, ".claude", "settings.local.json.example")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(crlf)
    first = run(project)
    write(project, ".claude/settings.local.json.example", '{"edited": true}')
    second = run(project)
    if first[1].get("SETTINGS_EXAMPLE_DRIFT") != "NO":
        return first, {"SETTINGS_EXAMPLE_DRIFT": "NO"}
    return second, {"SETTINGS_EXAMPLE_DRIFT": "YES"}


def case_mcp_servers(project):
    write(project, ".mcp.json", '{"mcpServers": {"playwright": {}, "xcode": {}}}')
    return run(project), {"MCP_SERVERS": "playwright,xcode"}


CASES = [
    ("a legacy project reports every leftover", case_legacy),
    ("BOM-prefixed files read the same as plain ones", case_bom),
    ("Serena's hooks count as obsolete even with serena-hooks installed", case_serena_installed),
    ("a null hook event does not crash it", case_null_event),
    ("unreadable files report UNKNOWN, never clean or ABSENT", case_corrupt),
    ("a non-object settings.local.json reports UNKNOWN", case_list_local),
    ("a clean project reports nothing", case_clean),
    ("an edited settings.local.json.example reports drift", case_example_drift),
    ("the servers in .mcp.json are listed for the §8 check", case_mcp_servers),
    ("a legacy docs/ui.md is reported", case_legacy_ui_md),
    ("docs/design/ itself is never a candidate", case_design_folder_is_not_legacy),
    ("design-named Markdown is found anywhere but dependencies and builds", case_design_named_docs_anywhere),
    ("a design-named folder with Markdown is one candidate", case_design_named_folder),
    ("an unreadable subdirectory is skipped, not UNKNOWN", case_unreadable_subdirectory),
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
    return pyhook.finish("detect-drift", bad, len(CASES), has_windows_form=False)


if __name__ == "__main__":
    sys.exit(main())
