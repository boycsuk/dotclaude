#!/usr/bin/env python3
"""Behavioural contract for `init --update --recursive <dir>` (scripts/update-projects.py).

Run:  python3 tests/update-projects-cases.py
      python3 tests/update-projects-cases.py --pwsh PATH   # through init.ps1 too

The recursive update touches many projects at once, so the contract is mostly
about what it must NOT do: find only dotclaude projects (never a dependency
folder, a nested project inside another, or a .claude/ dotclaude did not
write), change nothing on --dry-run or without a confirmation, keep every
server, permission and directory the user owns, and derive each project's
flags from what that project already has.
"""

import argparse
import hashlib
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
STUB = os.path.join(TEMPLATE_DIR, ".claude/settings.json")

LEGACY_HOOKS = {"PreToolUse": [
    {"matcher": "", "hooks": [{"type": "command", "command": "serena-hooks remind --client=claude-code"}]},
    {"matcher": "Bash", "hooks": [{"type": "command", "command": '"$HOME"/.claude/hooks/prefer-graphify.sh'}]},
]}
OLD_PLAYWRIGHT = {"command": "npx", "args": ["@playwright/mcp"], "env": {}}
MINE = {"command": "my-mcp", "args": [], "env": {}}


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(data if isinstance(data, str) else json.dumps(data, indent=2))


def stub_with(**extra):
    with open(STUB) as fh:
        data = json.load(fh)
    data.update(extra)
    return data


def build_tree(root):
    a = os.path.join(root, "a")
    write(os.path.join(a, ".claude/settings.json"), stub_with(
        hooks=LEGACY_HOOKS,
        permissions={"allow": ["mcp__serena__*", "mcp__graphify__*", "mcp__playwright__*", "Bash(make:*)"],
                     "ask": [], "deny": []}))
    write(os.path.join(a, ".mcp.json"), {"mcpServers": {
        "serena": {"command": "serena"}, "graphify": {"command": "uv"},
        "playwright": OLD_PLAYWRIGHT, "mine": MINE}})
    os.makedirs(os.path.join(a, ".serena", "memories"))
    write(os.path.join(a, "sub", ".claude/settings.json"), stub_with())          # nested: not visited
    b = os.path.join(root, "b")
    write(os.path.join(b, ".claude/settings.json"), {"permissions": {"allow": ["Bash(make:*)"]}})
    write(os.path.join(b, ".claude/settings.local.json.example"), "{}")
    write(os.path.join(b, ".mcp.json"), {"mcpServers": {"xcode": {"command": "xcrun", "args": ["mcpbridge"]}}})
    write(os.path.join(root, "node_modules", "c", ".claude/settings.json"), stub_with())  # dependency folder
    write(os.path.join(root, "plain", ".claude/settings.json"), "{}")                     # no dotclaude marker
    shutil.copytree(TEMPLATE_DIR, os.path.join(root, "clone", "templates", "project"))    # the template itself
    write(os.path.join(root, "deep/1/2/3/4/proj/.claude/settings.json"), stub_with())      # beyond depth 4
    return a, b


def snapshot(root):
    digest = {}
    for current, _, files in os.walk(root):
        for name in files:
            path = os.path.join(current, name)
            with open(path, "rb") as fh:
                digest[os.path.relpath(path, root)] = hashlib.sha256(fh.read()).hexdigest()
    return digest


def env_for(tmp):
    bindir = os.path.join(tmp, "bin")
    os.makedirs(bindir, exist_ok=True)
    npx = os.path.join(bindir, "npx")
    write(npx, "#!/bin/sh\nexit 0\n")
    os.chmod(npx, 0o755)
    clean = os.pathsep.join(d for d in os.environ["PATH"].split(os.pathsep)
                            if not os.path.exists(os.path.join(d, "serena-hooks")))
    return dict(os.environ, TEMPLATE_DIR=TEMPLATE_DIR, PATH=bindir + os.pathsep + clean)


def run(tmp, root, args, pwsh):
    cmd = ([pwsh, "-NoProfile", "-File", PS1] if pwsh else ["bash", SH]) + args
    return subprocess.run(cmd, cwd=root, env=env_for(tmp), capture_output=True, text=True,
                          stdin=subprocess.DEVNULL)


def load(path):
    with open(path) as fh:
        return json.load(fh)


def check(tmp, pwsh):
    root = os.path.join(tmp, "root")
    a, b = build_tree(root)
    # The folder of projects itself got a deploy by mistake (an init.sh too old
    # to know --recursive did exactly that): its projects must still be found.
    write(os.path.join(root, ".claude/settings.json"), stub_with())
    problems = []

    before = snapshot(root)
    proc = run(tmp, root, ["--update", "--recursive", ".", "--dry-run"], pwsh)
    listed = proc.stdout
    if proc.returncode != 0:
        problems.append(f"--dry-run exited {proc.returncode}: {proc.stderr[-300:]}")
    for rel, want in (("a", True), ("b", True), ("sub", False), ("node_modules", False),
                      ("plain", False), ("proj", False), ("templates/project", False)):
        if (f"\n  {rel}\n" in listed or f"\n  a/{rel}\n" in listed or f"/{rel}\n" in listed) != want:
            problems.append(f"--dry-run {'missed' if want else 'listed'} {rel!r}")
    if "\n  .\n" not in listed:
        problems.append("the root itself (a deployed folder) was not listed")
    if "--update --ui" not in listed:
        problems.append("project a: --ui not derived from its playwright server")
    if "serena, graphify" not in listed or ".serena" not in listed:
        problems.append("plan does not show the obsolete servers and directory")
    if snapshot(root) != before:
        problems.append("--dry-run changed files")

    proc = run(tmp, root, [root, "--update", "--recursive"], pwsh)       # directory first: order-independent
    if proc.returncode == 0 or snapshot(root) != before:
        problems.append("without a terminal and without --yes it must change nothing and exit non-zero")

    proc = run(tmp, root, ["--update", "--recursive", root, "--yes"], pwsh)
    if proc.returncode != 0 or "3 updated, 0 failed" not in proc.stdout:
        problems.append(f"--yes run: exit {proc.returncode}, out {proc.stdout[-400:]!r} err {proc.stderr[-300:]!r}")
    settings_a = load(os.path.join(a, ".claude/settings.json"))
    if "hooks" in settings_a:
        problems.append(f"project a: obsolete hooks survived: {settings_a['hooks']}")
    allow = settings_a.get("permissions", {}).get("allow", [])
    if allow != ["mcp__playwright__*", "Bash(make:*)"]:
        problems.append(f"project a: permissions wrong after removal: {allow}")
    servers_a = load(os.path.join(a, ".mcp.json"))["mcpServers"]
    if set(servers_a) != {"playwright", "mine"} or servers_a["mine"] != MINE:
        problems.append(f"project a: servers wrong: {servers_a}")
    if servers_a.get("playwright") == OLD_PLAYWRIGHT:
        problems.append("project a: --ui was not re-run (playwright spec not refreshed)")
    if not os.path.isdir(os.path.join(a, ".serena", "memories")):
        problems.append("project a: .serena/ was deleted (it may hold committed memories)")
    if load(os.path.join(b, ".mcp.json"))["mcpServers"].get("xcode", {}).get("command") != "xcrun":
        problems.append("project b: xcode server changed on a non-macOS host")
    if load(os.path.join(b, ".claude/settings.json")) != {"permissions": {"allow": ["Bash(make:*)"]}}:
        problems.append("project b: a user-owned settings.json was rewritten")
    for skipped in ("a/sub", "node_modules/c", "plain", "deep/1/2/3/4/proj", "clone/templates/project"):
        if os.path.exists(os.path.join(root, skipped, "CLAUDE.md")):
            problems.append(f"{skipped} was deployed into")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh", help="path to pwsh, to run init.ps1 too")
    args = ap.parse_args()
    bad = 0
    for label, pwsh in (("sh", None),) + ((("ps1", args.pwsh),) if args.pwsh else ()):
        tmp = tempfile.mkdtemp(prefix="update-projects-")
        try:
            problems = check(tmp, pwsh)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        bad += len(problems)
        print(f"  {'ok  ' if not problems else 'BAD '}[{label}] recursive update")
        for p in problems:
            print(f"        - {p}")
    print(f"\nupdate-projects: {'all checks pass' if not bad else f'{bad} problem(s)'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
