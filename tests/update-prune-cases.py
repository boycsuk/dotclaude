#!/usr/bin/env python3
"""Behavioural contract for obsolete-artifact pruning in init.{sh,ps1}.

Run:  python3 tests/update-prune-cases.py
      python3 tests/update-prune-cases.py --pwsh PATH   # through init.ps1 too

Removing a hook from dotclaude deletes its script from ~/.claude/hooks/ on the
next install, while projects deployed earlier still wire it in their settings
— so every matching tool call then fails with a hook error. Both init scripts
run templates/project/scripts/prune-obsolete.py to remove those entries. These
cases pin what it may and may not touch: only commands named in obsolete.json,
never a user's own hook, never a server or a directory (those are reported).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(REPO, "templates/project")
SH = os.path.join(TEMPLATE_DIR, "init.sh")
PS1 = os.path.join(TEMPLATE_DIR, "init.ps1")
PRUNE = os.path.join(TEMPLATE_DIR, "scripts/prune-obsolete.py")
MANIFEST = os.path.join(TEMPLATE_DIR, "obsolete.json")

USER_HOOK = {"type": "command", "command": "./scripts/my-own-check.sh"}
LEGACY_SH = {
    "SessionStart": [{"hooks": [{"type": "command", "command": "serena-hooks activate --client=claude-code"}]}],
    "PreToolUse": [
        {"matcher": "", "hooks": [{"type": "command", "command": "serena-hooks remind --client=claude-code"}]},
        {"matcher": "Bash", "hooks": [
            {"type": "command", "command": '"$HOME"/.claude/hooks/prefer-serena-bash.sh'},
            {"type": "command", "command": '"$HOME"/.claude/hooks/prefer-graphify.sh'},
            USER_HOOK]},
        {"matcher": "Read|Glob|Grep", "hooks": [
            {"type": "command", "command": '"$HOME"/.claude/hooks/prefer-graphify.sh'}]},
    ],
}
LEGACY_PS1 = {
    "PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "shell": "powershell",
         "command": '& "C:\\Users\\u\\.claude\\hooks\\prefer-graphify.ps1"'},
        {"type": "command", "shell": "powershell",
         "command": '& "/home/u/.claude\\hooks/prefer-serena-bash.ps1"'}]}],
}


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(data if isinstance(data, str) else json.dumps(data, indent=2))


def read_json(path):
    with open(path) as fh:
        return json.load(fh)


def run_init(project, pwsh):
    env = dict(os.environ, TEMPLATE_DIR=TEMPLATE_DIR)
    cmd = [pwsh, "-NoProfile", "-File", PS1] if pwsh else ["bash", SH]
    return subprocess.run(cmd, cwd=project, env=env, capture_output=True, text=True)


def all_commands(settings):
    return [h.get("command") for groups in settings.get("hooks", {}).values()
            for g in groups for h in g.get("hooks", [])]


def case_prunes_sh_form_keeps_user_hook(project, pwsh):
    path = os.path.join(project, ".claude/settings.json")
    write(path, {"permissions": {"allow": ["mcp__x__*"]}, "hooks": LEGACY_SH})
    if run_init(project, pwsh).returncode != 0:
        return "init exited non-zero"
    data = read_json(path)
    if all_commands(data) != [USER_HOOK["command"]]:
        return f"expected only the user hook to survive, got {all_commands(data)}"
    if set(data["hooks"]) != {"PreToolUse"}:
        return f"emptied events were not dropped: {sorted(data['hooks'])}"
    if data.get("permissions") != {"allow": ["mcp__x__*"]}:
        return "unrelated keys were changed"
    return None


def case_prunes_powershell_form(project, pwsh):
    path = os.path.join(project, ".claude/settings.json")
    write(path, {"hooks": LEGACY_PS1})
    if run_init(project, pwsh).returncode != 0:
        return "init exited non-zero"
    data = read_json(path)
    if "hooks" in data:
        return f"PowerShell-form obsolete hooks survived: {all_commands(data)}"
    return None


def case_prunes_settings_local(project, pwsh):
    path = os.path.join(project, ".claude/settings.local.json")
    write(path, {"allowPushToMain": True, "hooks": LEGACY_SH})
    if run_init(project, pwsh).returncode != 0:
        return "init exited non-zero"
    data = read_json(path)
    if data.get("allowPushToMain") is not True:
        return "personal opt-out was lost"
    if all_commands(data) != [USER_HOOK["command"]]:
        return f"settings.local.json not pruned: {all_commands(data)}"
    return None


def case_idempotent(project, pwsh):
    path = os.path.join(project, ".claude/settings.json")
    write(path, {"hooks": LEGACY_SH})
    run_init(project, pwsh)
    with open(path) as fh:
        first = fh.read()
    mtime = os.path.getmtime(path)
    if run_init(project, pwsh).returncode != 0:
        return "second init exited non-zero"
    with open(path) as fh:
        second = fh.read()
    if first != second or os.path.getmtime(path) != mtime:
        return "a second run rewrote an already-clean settings.json"
    return None


def case_clean_stub_untouched(project, pwsh):
    path = os.path.join(project, ".claude/settings.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    shutil.copy(os.path.join(TEMPLATE_DIR, ".claude/settings.json"), path)
    with open(path) as fh:
        before = fh.read()
    if run_init(project, pwsh).returncode != 0:
        return "init exited non-zero"
    with open(path) as fh:
        if fh.read() != before:
            return "a settings.json with nothing obsolete was rewritten"
    return None


def case_unparseable_is_left_alone(project, pwsh):
    path = os.path.join(project, ".claude/settings.json")
    write(path, '{"hooks": {,}')
    if run_init(project, pwsh).returncode != 0:
        return "init aborted on an unparseable settings.json"
    with open(path) as fh:
        if fh.read() != '{"hooks": {,}':
            return "an unparseable settings.json was modified"
    return None


def case_servers_and_files_only_reported(project, pwsh):
    write(os.path.join(project, ".mcp.json"),
          {"mcpServers": {"serena": {"command": "serena"}, "graphify": {"command": "uv"},
                          "mine": {"command": "x"}}})
    os.makedirs(os.path.join(project, "graphify-out"))
    if run_init(project, pwsh).returncode != 0:
        return "init exited non-zero"
    servers = set(read_json(os.path.join(project, ".mcp.json"))["mcpServers"])
    if servers != {"serena", "graphify", "mine"}:
        return f"init removed MCP servers on its own: {servers}"
    if not os.path.isdir(os.path.join(project, "graphify-out")):
        return "init deleted a user directory"
    out = subprocess.run([sys.executable, PRUNE, MANIFEST, project],
                         capture_output=True, text=True).stdout
    if "OBSOLETE_MCP=serena,graphify" not in out or "OBSOLETE_FILES=graphify-out" not in out:
        return f"report lines missing or wrong: {out!r}"
    return None


CASES = [
    ("sh-form obsolete hooks pruned, user hook kept", case_prunes_sh_form_keeps_user_hook),
    ("PowerShell-form obsolete hooks pruned", case_prunes_powershell_form),
    ("settings.local.json pruned, opt-outs kept", case_prunes_settings_local),
    ("second run is a no-op", case_idempotent),
    ("clean stub is byte-identical after deploy", case_clean_stub_untouched),
    ("unparseable settings: warn, never touch", case_unparseable_is_left_alone),
    ("servers and directories are reported, not removed", case_servers_and_files_only_reported),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh", help="path to pwsh, to run init.ps1 too")
    args = ap.parse_args()
    targets = [(None, "sh")] + ([(args.pwsh, "ps1")] if args.pwsh else [])
    total = bad = 0
    for pwsh, label in targets:
        for name, fn in CASES:
            project = tempfile.mkdtemp(prefix="prune-case-")
            try:
                problem = fn(project, pwsh)
            finally:
                shutil.rmtree(project, ignore_errors=True)
            total += 1
            bad += bool(problem)
            print(f"  {'ok  ' if not problem else 'BAD '}[{label}] {name}"
                  + (f" — {problem}" if problem else ""))
    print(f"\nupdate-prune: {total - bad} ok, {bad} bad")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
