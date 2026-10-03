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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stubs  # noqa: E402

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
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(data if isinstance(data, str) else json.dumps(data, indent=2))


def read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def read_json_sig(path):
    with open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


def clean_path():
    """PATH without any serena-hooks binary, so 'is Serena still installed?'
    depends on the case, not on the machine running the matrix."""
    return os.pathsep.join(d for d in os.environ["PATH"].split(os.pathsep)
                           if not os.path.exists(os.path.join(d, "serena-hooks")))


def run_init(project, pwsh):
    env = dict(os.environ, TEMPLATE_DIR=TEMPLATE_DIR, PATH=clean_path())
    cmd = [pwsh, "-NoProfile", "-File", PS1] if pwsh else ["bash", SH]
    return subprocess.run(cmd, cwd=project, env=env, capture_output=True, encoding="utf-8", errors="replace")


def all_commands(settings):
    return [h.get("command") for groups in settings.get("hooks", {}).values()
            for g in groups for h in g.get("hooks", [])]


def case_prunes_sh_form_keeps_user_hook(project, pwsh):
    path = os.path.join(project, ".claude/settings.json")
    write(path, {"_comment": "stub — keep", "permissions": {"allow": ["mcp__x__*"]}, "hooks": LEGACY_SH})
    if run_init(project, pwsh).returncode != 0:
        return "init exited non-zero"
    with open(path, encoding="utf-8") as fh:
        if "stub — keep" not in fh.read():
            return "non-ASCII text was escaped or lost in the rewrite"
    data = read_json(path)
    if all_commands(data) != [USER_HOOK["command"]]:
        return f"expected only the user hook to survive, got {all_commands(data)}"
    if set(data["hooks"]) != {"PreToolUse"}:
        return f"emptied events were not dropped: {sorted(data['hooks'])}"
    if data.get("permissions") != {"allow": ["mcp__x__*"]} or data.get("_comment") != "stub — keep":
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


def case_obsolete_allow_rule_removed(project, pwsh):
    # The playwright wildcard granted tools that must stay on ask; a deploy
    # removes it from allow, and never touches a deny the user wrote.
    path = os.path.join(project, ".claude/settings.json")
    write(path, {"permissions": {"allow": ["mcp__playwright__*", "Bash(make:*)"],
                                 "deny": ["mcp__playwright__*"]}})
    if run_init(project, pwsh).returncode != 0:
        return "init exited non-zero"
    perms = read_json(path)["permissions"]
    if perms["allow"] != ["Bash(make:*)"]:
        return f"allow not pruned as expected: {perms['allow']}"
    if perms["deny"] != ["mcp__playwright__*"]:
        return f"a user deny rule was touched: {perms['deny']}"
    return None


def case_bom_settings_are_pruned(project, pwsh):
    # utf-8-sig: settings saved by Notepad or PowerShell 5.1 start with a BOM.
    path = os.path.join(project, ".claude/settings.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig") as fh:
        json.dump({"hooks": LEGACY_SH}, fh)
    if run_init(project, pwsh).returncode != 0:
        return "init exited non-zero"
    return None if all_commands(read_json_sig(path)) == [USER_HOOK["command"]] else "a BOM file was not pruned"


def case_remove_mcp_is_exact(project, pwsh):
    # Removing the `serena` server must not strip rules of a server whose name
    # merely starts the same way.
    write(os.path.join(project, ".mcp.json"), {"mcpServers": {"serena": {}, "serenade": {}}})
    path = os.path.join(project, ".claude/settings.json")
    write(path, {"permissions": {"allow": ["mcp__serena__find", "mcp__serenade__run"]}})
    env = dict(os.environ, TEMPLATE_DIR=TEMPLATE_DIR, PATH=clean_path())
    cmd = ([pwsh, "-NoProfile", "-File", PS1] if pwsh else ["bash", SH]) + ["--update", "--remove-obsolete-mcp"]
    if subprocess.run(cmd, cwd=project, env=env, capture_output=True, encoding="utf-8", errors="replace").returncode != 0:
        return "init exited non-zero"
    allow = read_json(path)["permissions"]["allow"]
    servers = read_json(os.path.join(project, ".mcp.json"))["mcpServers"]
    if allow != ["mcp__serenade__run"] or set(servers) != {"serenade"}:
        return f"removal was not exact: allow={allow}, servers={sorted(servers)}"
    return None


def case_idempotent(project, pwsh):
    path = os.path.join(project, ".claude/settings.json")
    write(path, {"hooks": LEGACY_SH})
    run_init(project, pwsh)
    with open(path, encoding="utf-8") as fh:
        first = fh.read()
    mtime = os.path.getmtime(path)
    if run_init(project, pwsh).returncode != 0:
        return "second init exited non-zero"
    with open(path, encoding="utf-8") as fh:
        second = fh.read()
    if first != second or os.path.getmtime(path) != mtime:
        return "a second run rewrote an already-clean settings.json"
    return None


def case_clean_stub_untouched(project, pwsh):
    path = os.path.join(project, ".claude/settings.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    shutil.copy(os.path.join(TEMPLATE_DIR, ".claude/settings.json"), path)
    with open(path, encoding="utf-8") as fh:
        before = fh.read()
    if run_init(project, pwsh).returncode != 0:
        return "init exited non-zero"
    with open(path, encoding="utf-8") as fh:
        if fh.read() != before:
            return "a settings.json with nothing obsolete was rewritten"
    return None


def case_unparseable_is_left_alone(project, pwsh):
    path = os.path.join(project, ".claude/settings.json")
    write(path, '{"hooks": {,}')
    if run_init(project, pwsh).returncode != 0:
        return "init aborted on an unparseable settings.json"
    with open(path, encoding="utf-8") as fh:
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
    out = subprocess.run([sys.executable, PRUNE, MANIFEST, project], capture_output=True,
                         text=True, env=dict(os.environ, PATH=clean_path())).stdout
    if "OBSOLETE_MCP=serena,graphify" not in out or "OBSOLETE_FILES=graphify-out" not in out:
        return f"report lines missing or wrong: {out!r}"
    return None


def case_store_stub_python_is_skipped(project, pwsh):
    """Windows ships a "python3" alias that only opens the Microsoft Store and
    exits non-zero. init.ps1 took the first PATH match, ran the stub, and the
    prune silently did nothing. Only init.ps1 resolves interpreters this way."""
    if not pwsh:
        return None
    stub_dir = os.path.join(project, "stub-bin")
    stubs.write_stub(stub_dir, "python3", "Python was not found; run without arguments to install "
                                          "from the Microsoft Store\n", 9)
    path = os.path.join(project, ".claude/settings.json")
    write(path, {"hooks": LEGACY_SH})
    env = dict(os.environ, TEMPLATE_DIR=TEMPLATE_DIR, PATH=stub_dir + os.pathsep + clean_path())
    proc = subprocess.run([pwsh, "-NoProfile", "-File", PS1], cwd=project, env=env,
                          capture_output=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        return f"init exited {proc.returncode}"
    if all_commands(read_json(path)) != [USER_HOOK["command"]]:
        return "the Store stub was used: obsolete hooks were not pruned"
    return None


def case_serena_pruned_while_installed(project, pwsh):
    """Serena's hooks are pruned even where serena-hooks is still installed:
    dotclaude dropped Serena, and keeping its hooks made the recursive plan
    and the deploy disagree about what "obsolete" means."""
    stub_dir = os.path.join(project, "stub-bin")
    stubs.write_stub(stub_dir, "serena-hooks")
    path = os.path.join(project, ".claude/settings.json")
    write(path, {"hooks": LEGACY_SH})
    env = dict(os.environ, TEMPLATE_DIR=TEMPLATE_DIR, PATH=stub_dir + os.pathsep + clean_path())
    cmd = [pwsh, "-NoProfile", "-File", PS1] if pwsh else ["bash", SH]
    if subprocess.run(cmd, cwd=project, env=env, capture_output=True, encoding="utf-8", errors="replace").returncode != 0:
        return "init exited non-zero"
    commands = all_commands(read_json(path))
    if any("prefer-" in c for c in commands):
        return f"dotclaude's dead hooks survived: {commands}"
    if any("serena-hooks" in c for c in commands):
        return f"Serena's hooks survived because serena-hooks is on PATH: {commands}"
    return None


GRAPHIFY_COMMIT = "# graphify-hook-start\n# Installed by: graphify hook install\ngraphify update . || true\n# graphify-hook-end\n"
GRAPHIFY_CHECKOUT = "# graphify-checkout-hook-start\ngraphify update .\n# graphify-checkout-hook-end\n"


def case_graphify_git_hooks(project, pwsh):
    """`graphify hook install` (old init --serena) left git hooks that fail on
    every commit once Graphify is gone. Only its marked block may go: a hook
    with the user's own lines keeps them."""
    subprocess.run(["git", "init", "-q", project], check=True)
    hooks = os.path.join(project, ".git", "hooks")
    write(os.path.join(hooks, "post-commit"), "#!/bin/sh\n" + GRAPHIFY_COMMIT)
    write(os.path.join(hooks, "post-checkout"), "#!/bin/sh\necho mine\n" + GRAPHIFY_CHECKOUT + "echo also mine\n")
    write(os.path.join(hooks, "pre-push"), "#!/bin/sh\n# graphify-hook-start\nno end marker here\n")
    if run_init(project, pwsh).returncode != 0:
        return "init exited non-zero"
    if os.path.exists(os.path.join(hooks, "post-commit")):
        return "a hook holding only the graphify block was not removed"
    with open(os.path.join(hooks, "post-checkout"), encoding="utf-8") as fh:
        checkout = fh.read()
    if "graphify" in checkout or checkout.count("mine") != 2:
        return f"post-checkout should keep only the user's lines: {checkout!r}"
    with open(os.path.join(hooks, "pre-push"), encoding="utf-8") as fh:
        if "no end marker here" not in fh.read():
            return "a hook not listed in obsolete.json was touched"
    return None


CASES = [
    ("graphify git hooks: block removed, user lines kept", case_graphify_git_hooks),
    ("Serena's hooks are pruned even with serena-hooks installed", case_serena_pruned_while_installed),
    ("a Microsoft Store python3 stub does not silence the prune", case_store_stub_python_is_skipped),
    ("sh-form obsolete hooks pruned, user hook kept", case_prunes_sh_form_keeps_user_hook),
    ("PowerShell-form obsolete hooks pruned", case_prunes_powershell_form),
    ("settings.local.json pruned, opt-outs kept", case_prunes_settings_local),
    ("second run is a no-op", case_idempotent),
    ("an obsolete allow rule is removed, a deny kept", case_obsolete_allow_rule_removed),
    ("a BOM-prefixed settings file is pruned too", case_bom_settings_are_pruned),
    ("--remove-obsolete-mcp removes exactly the named server", case_remove_mcp_is_exact),
    ("clean stub is byte-identical after deploy", case_clean_stub_untouched),
    ("unparseable settings: warn, never touch", case_unparseable_is_left_alone),
    ("servers and directories are reported, not removed", case_servers_and_files_only_reported),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh", help="path to pwsh, to run init.ps1 too")
    args = ap.parse_args()
    targets = stubs.shell_targets(args.pwsh)
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
