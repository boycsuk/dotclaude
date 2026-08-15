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


def run_install(home, pwsh=None):
    env = dict(os.environ, HOME=home)
    if pwsh:
        cmd = [pwsh, "-NoProfile", "-File", PS1]
    else:
        cmd = ["bash", SH]
    p = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True)
    return p.returncode


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


CASES = [
    ("fresh install: settings, hooks, manifest", case_fresh_install),
    ("personal settings keys survive the merge", case_user_keys_survive),
    ("re-install keeps user-added files", case_rerun_keeps_user_files),
    ("stopped-shipping files are cleaned up", case_stopped_shipping_is_cleaned),
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
