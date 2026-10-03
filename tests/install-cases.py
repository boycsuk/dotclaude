#!/usr/bin/env python3
"""Behavioural contract for install.{sh,ps1}.

Run:  python3 tests/install-cases.py
      python3 tests/install-cases.py --pwsh PATH   # verify parity

The installers hold the single strongest invariant in the repo docs — merging
the central settings.json into the user's WITHOUT clobbering their personal
keys — plus the manifest add/remove cycle that lets a re-install clean up
files the repo stopped shipping while never touching files the user added.
None of it had a net: the BSD-find manifest break shipped precisely because
nothing executed install.sh outside the author's machine.

Each case runs the real installer against a throwaway HOME (set in the parent
environment — $HOME is read-only INSIDE a PowerShell session, see CLAUDE.md).
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SH = os.path.join(REPO, "install.sh")
PS1 = os.path.join(REPO, "install.ps1")


def run_install(home, pwsh=None, repo=REPO):
    env = dict(os.environ, HOME=home)
    if pwsh:
        cmd = [pwsh, "-NoProfile", "-File", os.path.join(repo, "install.ps1")]
    else:
        cmd = ["bash", os.path.join(repo, "install.sh")]
    p = subprocess.run(cmd, cwd=repo, env=env, capture_output=True, text=True)
    LAST_OUTPUT[0] = p.stdout + p.stderr
    return p.returncode


LAST_OUTPUT = [""]


def claude(home, *parts):
    return os.path.join(home, ".claude", *parts)


def case_fresh_install(home, pwsh):
    if run_install(home, pwsh) != 0:
        return "installer exited non-zero"
    try:
        with open(claude(home, "settings.json")) as fh:
            json.load(fh)
    except (OSError, ValueError) as e:
        return f"settings.json unreadable after install: {e}"
    keep, drop = (".ps1", ".sh") if pwsh else (".sh", ".ps1")
    hooks = os.listdir(claude(home, "hooks"))
    if not any(h.endswith(keep) for h in hooks):
        return f"no {keep} hooks installed"
    if any(h.endswith(drop) for h in hooks):
        return f"{drop} siblings not stripped from hooks/"
    manifest = claude(home, ".dotclaude-manifest")
    if not os.path.exists(manifest):
        return "manifest missing"
    with open(manifest) as fh:
        for line in fh:
            rel = line.strip()
            if rel and not os.path.exists(claude(home, rel)):
                return f"manifest lists {rel} but it does not exist on disk"
    return None


def case_user_keys_survive(home, pwsh):
    os.makedirs(claude(home), exist_ok=True)
    with open(claude(home, "settings.json"), "w") as fh:
        json.dump({"model": "user-model", "outputStyle": "dotclaude",
                   "permissions": {"allow": ["Bash(user-added:*)"]}}, fh)
    if run_install(home, pwsh) != 0:
        return "installer exited non-zero"
    with open(claude(home, "settings.json")) as fh:
        merged = json.load(fh)
    if merged.get("model") != "user-model":
        return "personal 'model' key was clobbered"
    if merged.get("outputStyle") != "dotclaude":
        return "personal 'outputStyle' key was clobbered"
    if merged.get("fileCheckpointingEnabled") is not True:
        return "a seeded key was not written on a settings.json that lacked it"
    # permissions is a repo-OWNED key: the user's ad-hoc edit must be replaced
    # by the central set, not merged into it.
    if "Bash(user-added:*)" in merged.get("permissions", {}).get("allow", []):
        return "repo-owned 'permissions' kept a user edit (should be replaced)"
    if not merged.get("permissions", {}).get("deny"):
        return "central deny list missing after merge"
    return None


def case_rerun_keeps_user_files(home, pwsh):
    if run_install(home, pwsh) != 0:
        return "first install failed"
    mine = claude(home, "skills", "my-own-skill", "SKILL.md")
    os.makedirs(os.path.dirname(mine), exist_ok=True)
    with open(mine, "w") as fh:
        fh.write("---\nname: my-own-skill\n---\n")
    if run_install(home, pwsh) != 0:
        return "re-install failed"
    if not os.path.exists(mine):
        return "user-added skill was deleted by a re-install"
    return None


def case_stopped_shipping_is_cleaned(home, pwsh):
    if run_install(home, pwsh) != 0:
        return "first install failed"
    ext = "ps1" if pwsh else "sh"
    ghost = claude(home, "hooks", f"ghost.{ext}")
    with open(ghost, "w") as fh:
        fh.write("exit 0\n")
    with open(claude(home, ".dotclaude-manifest"), "a") as fh:
        fh.write(f"hooks/ghost.{ext}\n")
    if run_install(home, pwsh) != 0:
        return "re-install failed"
    if os.path.exists(ghost):
        return "a file the repo stopped shipping survived the re-install"
    if f"retired hooks removed: ghost.{ext}" not in LAST_OUTPUT[0]:
        return "no notice that a retired hook may still be wired in projects"
    return None


def case_seeded_on_fresh(home, pwsh):
    """A fresh machine gets the seeded defaults, or shipping them is pointless:
    that was the outputStyle gap — the style file was installed but nothing
    ever activated it."""
    if run_install(home, pwsh) != 0:
        return "installer exited non-zero"
    with open(claude(home, "settings.json")) as fh:
        merged = json.load(fh)
    src = os.path.join(REPO, "global/.claude/settings.json")
    with open(src) as fh:
        want = {k: v for k, v in json.load(fh).items()
                if k in ("outputStyle", "fileCheckpointingEnabled")}
    for key, value in want.items():
        if merged.get(key) != value:
            return f"seeded key '{key}' missing or wrong: {merged.get(key)!r} != {value!r}"
    if any(k.startswith("_") for k in merged):
        return "a _comment key leaked into the installed settings.json"
    return None


def case_seeded_never_reverts_user_choice(home, pwsh):
    """The whole reason these are seeded and not owned: a re-install after a
    /config change must not revert it."""
    if run_install(home, pwsh) != 0:
        return "first install failed"
    with open(claude(home, "settings.json")) as fh:
        merged = json.load(fh)
    merged["outputStyle"] = "Explanatory"
    merged["fileCheckpointingEnabled"] = False
    with open(claude(home, "settings.json"), "w") as fh:
        json.dump(merged, fh)
    if run_install(home, pwsh) != 0:
        return "re-install failed"
    with open(claude(home, "settings.json")) as fh:
        after = json.load(fh)
    if after.get("outputStyle") != "Explanatory":
        return "re-install reverted the user's outputStyle choice"
    if after.get("fileCheckpointingEnabled") is not False:
        return "re-install reverted the user's fileCheckpointingEnabled choice"
    if not after.get("permissions", {}).get("deny"):
        return "owned keys stopped being applied"
    return None


def case_unparseable_settings_backed_up(home, pwsh):
    os.makedirs(claude(home), exist_ok=True)
    with open(claude(home, "settings.json"), "w") as fh:
        fh.write("{ this is not json")
    if run_install(home, pwsh) != 0:
        return "installer aborted on an unparseable settings.json"
    if not glob.glob(claude(home, "settings.json.bak-*")):
        return "no backup of the unparseable settings.json"
    try:
        with open(claude(home, "settings.json")) as fh:
            json.load(fh)
    except (OSError, ValueError) as e:
        return f"settings.json still unreadable after install: {e}"
    return None


FIXTURE_HOOK = '''\
import os, sys
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))
import hookio
payload = hookio.read_payload()
hookio.context("SessionStart", "fixture-ok:" + payload.get("probe", ""))
'''


def case_python_hook_installed_and_runs(home, pwsh):
    # A .py hook is the one artifact whose Windows wiring is not a file swap:
    # install.ps1 rewrites its command to the interpreter it verified. Prove
    # the installed command actually runs, through the shell that runs it.
    repo = tempfile.mkdtemp(prefix="install-repo-")
    try:
        for item in ("install.sh", "install.ps1", "global", "templates", "skills"):
            src = os.path.join(REPO, item)
            dst = os.path.join(repo, item)
            (shutil.copytree if os.path.isdir(src) else shutil.copy2)(src, dst)
        with open(os.path.join(repo, "global/.claude/hooks/fixture-echo.py"), "w") as fh:
            fh.write(FIXTURE_HOOK)
        settings_src = os.path.join(repo, "global/.claude/settings.json")
        with open(settings_src) as fh:
            settings = json.load(fh)
        settings["hooks"].setdefault("SessionStart", []).append({"hooks": [{
            "type": "command", "timeout": 5,
            "command": 'python3 "$HOME"/.claude/hooks/fixture-echo.py'}]})
        with open(settings_src, "w") as fh:
            json.dump(settings, fh, indent=2)

        if run_install(home, pwsh, repo) != 0:
            return "installer exited non-zero"
        for rel in ("hooks/fixture-echo.py", "hooks/_lib/hookio.py", "hooks/_lib/shellwords.py"):
            if not os.path.exists(claude(home, rel)):
                return f"{rel} was not installed"
        with open(claude(home, ".dotclaude-manifest")) as fh:
            listed = {line.strip() for line in fh}
        if "hooks/_lib/hookio.py" not in listed:
            return "hooks/_lib/ is not in the manifest, so a re-install could never clean it up"
        with open(claude(home, "settings.json")) as fh:
            installed = json.load(fh)
        commands = [h["command"] for g in installed["hooks"].get("SessionStart", [])
                    for h in g["hooks"] if "fixture-echo" in h["command"]]
        if len(commands) != 1:
            return f"expected one wired fixture hook, found {commands}"
        if pwsh:
            runner = [pwsh, "-NoProfile", "-Command", commands[0]]
        else:
            runner = ["bash", "-c", commands[0]]
        proc = subprocess.run(runner, input='{"probe": "x"}', capture_output=True,
                              text=True, env=dict(os.environ, HOME=home))
        if proc.returncode != 0 or "fixture-ok:x" not in proc.stdout:
            return (f"installed command did not run cleanly: rc={proc.returncode} "
                    f"out={proc.stdout.strip()!r} err={proc.stderr.strip()[:200]!r}")
        if glob.glob(claude(home, "hooks", "**", "__pycache__"), recursive=True):
            return "a __pycache__ appeared under hooks/ (unmanaged files in a repo-owned tree)"
    finally:
        shutil.rmtree(repo, ignore_errors=True)
    return None


def case_installed_guard_blocks(home, pwsh):
    # The matrices run each hook from the repo; this runs the commands the
    # installer WROTE, exactly as Claude Code launches them. Under PowerShell,
    # `-Command '& "x.ps1"'` turned a script's exit 2 into exit 1, which does
    # not block — every .ps1 guard shipped that way while its matrix, run
    # through `-File`, passed. A .py guard blocks with a JSON deny instead.
    if run_install(home, pwsh) != 0:
        return "installer exited non-zero"
    with open(claude(home, "settings.json")) as fh:
        installed = json.load(fh)
    tool = "PowerShell" if pwsh else "Bash"
    probes = [
        ("guard-destructive", {"tool_name": tool, "tool_input": {"command": "rm -rf /"}}),
        ("guard-central-config", {"tool_name": "Edit", "tool_input": {
            "file_path": os.path.join(home, ".claude", "settings.json"),
            "old_string": "a", "new_string": "b"}}),
    ]
    for name, payload in probes:
        commands = [h["command"] for g in installed["hooks"].get("PreToolUse", [])
                    for h in g["hooks"] if name in h["command"]]
        if len(commands) != 1:
            return f"expected one wired {name} hook, found {commands}"
        if pwsh:
            runner = [pwsh, "-NoProfile", "-NonInteractive", "-Command", commands[0]]
        else:
            runner = ["bash", "-c", commands[0]]
        proc = subprocess.run(runner, input=json.dumps(payload), capture_output=True, text=True,
                              env=dict(os.environ, HOME=home))
        denied = '"permissionDecision": "deny"' in proc.stdout
        if proc.returncode != 2 and not denied:
            return (f"installed {name} did not block (exit {proc.returncode}, no deny on stdout); "
                    f"err={proc.stderr.strip()[:200]!r}")
    return None


def case_shell_guards_cover_both_tools(home, pwsh):
    # With Git for Windows the Bash tool stays available next to PowerShell.
    # install.ps1 used to RENAME the Bash matcher and replace every Bash rule,
    # so Git Bash calls ran with no guard and no deny on Windows.
    if run_install(home, pwsh) != 0:
        return "installer exited non-zero"
    with open(claude(home, "settings.json")) as fh:
        installed = json.load(fh)
    guard_groups = [g for g in installed["hooks"].get("PreToolUse", [])
                    if any("guard-destructive" in h["command"] for h in g["hooks"])]
    if len(guard_groups) != 1:
        return f"expected one group wiring guard-destructive, found {len(guard_groups)}"
    tools = set(guard_groups[0].get("matcher", "").split("|"))
    if not {"Bash", "PowerShell"} <= tools:
        return f"shell guards match {sorted(tools)}, not both Bash and PowerShell"
    deny = installed["permissions"]["deny"]
    if not any(r.startswith("Bash(rm -rf") for r in deny):
        return "the Bash rm -rf deny rule is missing"
    if pwsh:
        if not any(r.startswith("PowerShell(Remove-Item") for r in deny):
            return "the PowerShell Remove-Item deny rule is missing"
        if "PowerShell(Remove-Item *)" in deny:
            return "PowerShell(Remove-Item *) denies every single-file delete"
    return None


def case_statusline_runs_under_any_shell(home, pwsh):
    if not pwsh:
        return None
    # statusLine has no `shell` key; with Git Bash installed Claude Code runs
    # the command through bash, where `& "C:\..."` is a syntax error. An
    # earlier install seeded exactly that, so a re-install must repair it.
    legacy = '& "' + claude(home) + '\\hooks\\statusline.ps1"'
    os.makedirs(claude(home), exist_ok=True)
    with open(claude(home, "settings.json"), "w") as fh:
        json.dump({"statusLine": {"type": "command", "command": legacy, "shell": "powershell"}}, fh)
    if run_install(home, pwsh) != 0:
        return "installer exited non-zero"
    with open(claude(home, "settings.json")) as fh:
        status = json.load(fh).get("statusLine", {})
    if "shell" in status or status.get("command", "").startswith("&"):
        return f"statusLine still in the bash-incompatible form: {status}"
    custom = {"type": "command", "command": "my-own-status"}
    with open(claude(home, "settings.json"), "w") as fh:
        json.dump({"statusLine": custom}, fh)
    if run_install(home, pwsh) != 0:
        return "re-install exited non-zero"
    with open(claude(home, "settings.json")) as fh:
        if json.load(fh).get("statusLine") != custom:
            return "a re-install replaced the user's own status line"
    return None


def _read(path):
    with open(path, "rb") as fh:
        return fh.read()


def case_reinstall_is_idempotent(home, pwsh):
    # A re-install that changes nothing must write nothing: a merge that
    # appended hook groups instead of replacing them doubled every guard on
    # each run, and the matrices never ran the installer twice.
    for _ in range(2):
        if run_install(home, pwsh) != 0:
            return "installer exited non-zero"
    first = (_read(claude(home, "settings.json")), _read(claude(home, ".dotclaude-manifest")))
    if run_install(home, pwsh) != 0:
        return "third install exited non-zero"
    second = (_read(claude(home, "settings.json")), _read(claude(home, ".dotclaude-manifest")))
    if first != second:
        return "a re-install changed settings.json or the manifest"
    leftovers = glob.glob(claude(home, "settings.json.bak-*")) + glob.glob(
        claude(home, "**", "*.user-backup"), recursive=True)
    if leftovers:
        return f"a plain re-install made backups of dotclaude's own output: {leftovers}"
    return None


def case_user_files_in_shared_trees_survive(home, pwsh):
    # The trees are shared with the user. A glob delete of the other
    # platform's hook siblings took the user's own hooks, and pruning every
    # empty directory took a skill they had just started.
    own = [claude(home, "hooks", "my-own.ps1"), claude(home, "hooks", "my-own.sh")]
    for path in own:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write("# mine\n")
    os.makedirs(claude(home, "skills", "my-wip"))
    for _ in range(2):
        if run_install(home, pwsh) != 0:
            return "installer exited non-zero"
    missing = [p for p in own + [claude(home, "skills", "my-wip")] if not os.path.exists(p)]
    return f"the user's own files were deleted: {missing}" if missing else None


def case_same_named_user_file_is_backed_up(home, pwsh):
    mine = claude(home, "agents", "researcher.md")
    os.makedirs(os.path.dirname(mine))
    with open(mine, "w") as fh:
        fh.write("my own researcher\n")
    if run_install(home, pwsh) != 0:
        return "installer exited non-zero"
    backup = mine + ".user-backup"
    if not os.path.exists(backup) or _read(backup) != b"my own researcher\n":
        return "a user file sharing a shipped name was overwritten without a backup"
    if "user-backup" not in LAST_OUTPUT[0]:
        return "the backup was made silently"
    return None


def case_replaced_owned_keys_are_backed_up(home, pwsh):
    os.makedirs(claude(home))
    with open(claude(home, "settings.json"), "w") as fh:
        json.dump({"theme": "dark", "permissions": {"deny": ["Read(~/.ssh/**)"]}}, fh)
    if run_install(home, pwsh) != 0:
        return "installer exited non-zero"
    backups = glob.glob(claude(home, "settings.json.bak-*"))
    if len(backups) != 1 or b"Read(~/.ssh/**)" not in _read(backups[0]):
        return f"the user's own deny rule was replaced with no backup: {backups}"
    if "was replaced" not in LAST_OUTPUT[0]:
        return "the replacement was not reported"
    with open(claude(home, "settings.json")) as fh:
        if json.load(fh).get("theme") != "dark":
            return "a personal key was lost"
    return None


def case_manifest_cannot_escape_claude_dir(home, pwsh):
    if run_install(home, pwsh) != 0:
        return "installer exited non-zero"
    victim = os.path.join(home, "victim")
    with open(victim, "w") as fh:
        fh.write("keep\n")
    with open(claude(home, ".dotclaude-manifest"), "a") as fh:
        fh.write("../victim\nhooks/../../victim\n\n")
    if run_install(home, pwsh) != 0:
        return "re-install exited non-zero"
    return None if os.path.exists(victim) else "a manifest line with .. deleted a file outside ~/.claude"


def case_broken_hook_aborts_before_copying(home, pwsh):
    # A hook that does not parse is a wall (every Bash call fails) and a .py
    # one that does not compile is a guard silently off. Either must stop the
    # install with the previous, working hooks still in place.
    if run_install(home, pwsh) != 0:
        return "first install exited non-zero"
    before = {p: _read(p) for p in glob.glob(claude(home, "hooks", "**", "*"), recursive=True)
              if os.path.isfile(p)}
    for broken, text in (("guard-commit.py", "\ndef broken(:\n"),
                         ("verify-on-edit.ps1" if pwsh else "verify-on-edit.sh",
                          "\nif ($x) {\n" if pwsh else "\nif true; then\n")):
        repo = tempfile.mkdtemp(prefix="install-repo-")
        try:
            for item in ("install.sh", "install.ps1", "global", "templates", "skills"):
                src = os.path.join(REPO, item)
                (shutil.copytree if os.path.isdir(src) else shutil.copy2)(src, os.path.join(repo, item))
            with open(os.path.join(repo, "global/.claude/hooks", broken), "a") as fh:
                fh.write(text)
            if run_install(home, pwsh, repo) == 0:
                return f"the installer accepted a broken {broken}"
        finally:
            shutil.rmtree(repo, ignore_errors=True)
        after = {p: _read(p) for p in glob.glob(claude(home, "hooks", "**", "*"), recursive=True)
                 if os.path.isfile(p)}
        if after != before:
            return f"a broken {broken} still changed the installed hooks"
    return None


def case_installed_template_deploys(home, pwsh):
    # Every deployer matrix points TEMPLATE_DIR at the repo, so none of them
    # ran the template from where install puts it, the way users do.
    if run_install(home, pwsh) != 0:
        return "installer exited non-zero"
    for rel in ("skills/init-project/SKILL.md", "skills/init-project/scripts/detect-drift.py",
                "templates/project/init.sh" if not pwsh else "templates/project/init.ps1"):
        if not os.path.exists(claude(home, rel)):
            return f"{rel} was not installed"
    project = tempfile.mkdtemp(prefix="install-project-")
    try:
        env = {k: v for k, v in os.environ.items() if k != "TEMPLATE_DIR"}
        env["HOME"] = home
        if pwsh:
            cmd = [pwsh, "-NoProfile", "-File", claude(home, "templates", "project", "init.ps1")]
        else:
            cmd = ["bash", claude(home, "templates", "project", "init.sh")]
        proc = subprocess.run(cmd, cwd=project, env=env, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL)
        if proc.returncode != 0 or not os.path.exists(os.path.join(project, "CLAUDE.md")):
            return f"the installed template did not deploy (exit {proc.returncode}): {proc.stderr[-200:]}"
    finally:
        shutil.rmtree(project, ignore_errors=True)
    return None


def case_output_style_defaults_on(home, pwsh):
    if run_install(home, pwsh) != 0:
        return "installer exited non-zero"
    with open(claude(home, "settings.json")) as fh:
        if json.load(fh).get("outputStyle") != "dotclaude":
            return "a fresh install did not enable the dotclaude output style"
    with open(claude(home, "settings.json")) as fh:
        settings = json.load(fh)
    settings["outputStyle"] = "Explanatory"
    with open(claude(home, "settings.json"), "w") as fh:
        json.dump(settings, fh)
    if run_install(home, pwsh) != 0:
        return "re-install exited non-zero"
    with open(claude(home, "settings.json")) as fh:
        if json.load(fh).get("outputStyle") != "Explanatory":
            return "a re-install overrode the output style the user chose"
    return None


CASES = [
    ("output style defaults on, a user choice is kept", case_output_style_defaults_on),
    ("a .py hook is installed, manifested and runs as wired", case_python_hook_installed_and_runs),
    ("an installed guard blocks through its wired command", case_installed_guard_blocks),
    ("a re-install is byte-for-byte idempotent", case_reinstall_is_idempotent),
    ("the user's own hooks and empty dirs survive", case_user_files_in_shared_trees_survive),
    ("a same-named user file is backed up, not lost", case_same_named_user_file_is_backed_up),
    ("replaced owned keys are backed up and reported", case_replaced_owned_keys_are_backed_up),
    ("the manifest cannot delete outside ~/.claude", case_manifest_cannot_escape_claude_dir),
    ("a broken hook aborts before anything is copied", case_broken_hook_aborts_before_copying),
    ("the installed template deploys a project", case_installed_template_deploys),
    ("shell guards and rules cover both Bash and PowerShell", case_shell_guards_cover_both_tools),
    ("the status line runs under any shell, a broken seed is repaired", case_statusline_runs_under_any_shell),
    ("fresh install: settings, hooks, manifest", case_fresh_install),
    ("personal settings keys survive the merge", case_user_keys_survive),
    ("re-install keeps user-added files", case_rerun_keeps_user_files),
    ("stopped-shipping files are cleaned up", case_stopped_shipping_is_cleaned),
    ("seeded defaults land on a fresh machine", case_seeded_on_fresh),
    ("a re-install never reverts a seeded choice", case_seeded_never_reverts_user_choice),
    ("unparseable settings is backed up, not lost", case_unparseable_settings_backed_up),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh", help="path to pwsh, to verify install.ps1 too")
    args = ap.parse_args()

    targets = [(None, "sh")]
    if args.pwsh:
        targets.append((args.pwsh, "ps1"))

    total = bad = 0
    for pwsh, label in targets:
        for name, fn in CASES:
            home = tempfile.mkdtemp(prefix="install-case-")
            try:
                problem = fn(home, pwsh)
            finally:
                shutil.rmtree(home, ignore_errors=True)
            total += 1
            if problem:
                bad += 1
            status = "ok  " if problem is None else "BAD "
            print(f"  {status}[{label}] {name}" + (f" — {problem}" if problem else ""))

    print(f"\ninstall: {total - bad} ok, {bad} bad")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
