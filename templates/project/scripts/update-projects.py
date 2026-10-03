#!/usr/bin/env python3
"""Re-deploy (--update) every dotclaude project under a directory.

Started by `init.sh --update --recursive <dir>` or the init.ps1 equivalent,
which pass their own path so each project is updated by the same script the
user would run by hand:

    python3 update-projects.py <dir> --init <init.sh|init.ps1> [--pwsh <exe>] [--yes] [--dry-run] [--depth N]

1. Find projects: a directory whose .claude/ carries a dotclaude marker — the
   template settings stub, settings.local.json.example, or a hook entry
   obsolete.json lists. Dependency and VCS folders are skipped, and the walk
   does not descend into a project it already found.
2. Detect each project's flags from what it already has: .mcp.json servers
   map back to --xcode / --ui / --codebase-memory (--xcode only on macOS,
   where it can run; elsewhere the server is kept as it is).
3. Show the plan — flags, obsolete hooks, obsolete servers (removed),
   obsolete directories (listed, never deleted) — and ask before touching
   anything, unless --yes. --dry-run stops after the plan.
4. Run `init --update <flags> --remove-obsolete-mcp` in each project and
   summarise, echoing each project's WARN and DRIFT lines. Exit 10 if any
   project failed, 11 if the run was cancelled or could not ask.
"""

import argparse
import importlib.util
import os
import platform
import subprocess
import sys

sys.dont_write_bytecode = True

STUB_MARKER = "Per-project settings ONLY"
SKIP_DIRS = {".git", "node_modules", "vendor", ".venv", "venv", "__pycache__", "dist",
             "build", "target", ".next", ".cache", ".tox", "site-packages", "Pods"}
SERVER_FLAGS = {"playwright": "--ui", "codebase-memory-mcp": "--codebase-memory", "xcode": "--xcode"}
EXIT_FAILED, EXIT_CANCELLED = 10, 11       # documented in init.sh; 1 means "template missing"

# The deploy prunes with prune-obsolete.py; planning with the same functions is
# what keeps "obsolete hooks: N (pruned)" true.
_spec = importlib.util.spec_from_file_location(
    "prune_obsolete", os.path.join(os.path.dirname(os.path.abspath(__file__)), "prune-obsolete.py"))
prune = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prune)


def load(path):
    try:
        return prune.load(path)
    except (OSError, ValueError):
        return None


def obsolete_hook_count(project, matches):
    return prune.count_obsolete_hooks(project, matches) or 0


def is_project(path, matches):
    claude = os.path.join(path, ".claude")
    # The template itself (a dotclaude clone, ~/.claude/templates/project) ships
    # the same stub; updating it would seed a CLAUDE.md into the template.
    if not os.path.isdir(claude) or os.path.exists(os.path.join(path, "CLAUDE.md.template")):
        return False
    try:
        with open(os.path.join(claude, "settings.json"), encoding="utf-8-sig") as fh:
            if STUB_MARKER in fh.read():
                return True
    except OSError:
        pass
    return (os.path.exists(os.path.join(claude, "settings.local.json.example"))
            or obsolete_hook_count(path, matches) > 0)


def find_projects(root, matches, depth):
    found = []
    root = os.path.abspath(root)
    for current, dirs, _ in os.walk(root):
        level = current[len(root):].count(os.sep)
        if is_project(current, matches):
            found.append(current)
            # Never stop at the root: a folder of projects that was once
            # deployed into by mistake still has its projects underneath.
            if current != root:
                dirs[:] = []
                continue
        if level >= depth:
            dirs[:] = []
            continue
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
    return found


def plan_for(project, manifest):
    mcp = load(os.path.join(project, ".mcp.json"))
    servers = mcp.get("mcpServers") if isinstance(mcp, dict) else None
    servers = servers if isinstance(servers, dict) else {}
    flags, notes = [], []
    for server, flag in SERVER_FLAGS.items():
        if server not in servers:
            continue
        if flag == "--xcode" and platform.system() != "Darwin":
            notes.append("xcode server kept as is (only refreshed on macOS)")
            continue
        flags.append(flag)
    obsolete_servers = [s["name"] for s in manifest.get("mcpServers", []) if s.get("name") in servers]
    obsolete_dirs = [f["path"] for f in manifest.get("files", [])
                     if os.path.exists(os.path.join(project, f.get("path", "")))]
    matches = prune.hook_matches(manifest)
    return {"project": project, "flags": flags, "notes": notes,
            "hooks": obsolete_hook_count(project, matches),
            "servers": obsolete_servers, "dirs": obsolete_dirs}


def print_plan(plans, root):
    print(f"dotclaude projects under {root}: {len(plans)}")
    for p in plans:
        rel = os.path.relpath(p["project"], root)
        print(f"\n  {rel}")
        print(f"    flags:            --update {' '.join(p['flags'])}".rstrip())
        if p["hooks"]:
            print(f"    obsolete hooks:   {p['hooks']} (pruned)")
        if p["servers"]:
            print(f"    obsolete servers: {', '.join(p['servers'])} (removed from .mcp.json with their permissions)")
        if p["dirs"]:
            print(f"    obsolete dirs:    {', '.join(p['dirs'])} (listed only — delete them yourself if unused)")
        for note in p["notes"]:
            print(f"    note:             {note}")


def run_init(init, pwsh, project, flags):
    args = ["--update"] + flags + ["--remove-obsolete-mcp"]
    if init.endswith(".ps1"):
        cmd = [pwsh or "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", init] + args
    else:
        cmd = ["bash", init] + args
    return subprocess.run(cmd, cwd=project, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("root")
    ap.add_argument("--init", required=True, help="path of the init.sh or init.ps1 to run per project")
    ap.add_argument("--pwsh", help="PowerShell executable for init.ps1")
    ap.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    ap.add_argument("--dry-run", action="store_true", help="show the plan and stop")
    ap.add_argument("--depth", type=int, default=4, help="how many directory levels to search (default 4)")
    args = ap.parse_args()

    if not os.path.isdir(args.root):
        print(f"ERROR: {args.root} is not a directory", file=sys.stderr)
        return 2
    manifest = load(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "obsolete.json")) or {}
    matches = prune.hook_matches(manifest)
    root = os.path.abspath(args.root)
    plans = [plan_for(p, manifest) for p in find_projects(root, matches, args.depth)]
    print_plan(plans, root)
    if not plans or args.dry_run:
        return 0

    if not args.yes:
        if not sys.stdin.isatty():
            print("\nNot a terminal and no --yes: nothing changed.", file=sys.stderr)
            return EXIT_CANCELLED
        answer = input(f"\nUpdate these {len(plans)} project(s)? [s/N] ").strip().lower()
        if answer not in ("s", "si", "sí", "y", "yes"):
            print("Cancelled: nothing changed.")
            return EXIT_CANCELLED

    failed = []
    print()
    for p in plans:
        rel = os.path.relpath(p["project"], root)
        proc = run_init(args.init, args.pwsh, p["project"], p["flags"])
        ok = proc.returncode == 0
        print(f"  {'ok    ' if ok else 'FAILED'} {rel}" + ("" if ok else f" (exit {proc.returncode})"))
        # A deploy that succeeded can still have warned (a broken .mcp.json, a
        # missing language server) or drifted; those lines must not vanish.
        for line in (proc.stderr or "").splitlines() if ok else []:
            if line.startswith(("WARN:", "DRIFT:")):
                print(f"           {line}")
        if not ok:
            failed.append(rel)
            tail = (proc.stderr or proc.stdout).strip().splitlines()[-5:]
            for line in tail:
                print(f"           {line}")
    leftovers = [(os.path.relpath(p["project"], root), d) for p in plans for d in p["dirs"]]
    if leftovers:
        print("\nObsolete directories left in place (delete them yourself when unused):")
        for rel, d in leftovers:
            print(f"  {os.path.join(rel, d)}")
    print(f"\n{len(plans) - len(failed)} updated, {len(failed)} failed.")
    return EXIT_FAILED if failed else 0


if __name__ == "__main__":
    sys.exit(main())
