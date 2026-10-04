#!/usr/bin/env python3
"""Behavioural contract for what init.{sh,ps1} write into a project.

Run:  python3 tests/init-seed-cases.py
      python3 tests/init-seed-cases.py --pwsh PATH   # through init.ps1 too

The deployer's core promise is "seed only what is missing, never overwrite the
user's files", and `--update --recursive --yes` applies it to every project
under a directory at once. A 2026-10-03 mutation audit found it had no net:
making CLAUDE.md, CHANGELOG.md, docs/ or the scaffolds overwrite, sorting the
.gitignore, or overwriting an edited settings.local.json.example all passed
every matrix. These cases run the real init script in a throwaway project.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyhook  # noqa: E402
import stubs  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(REPO, "templates/project")
SH = os.path.join(TEMPLATE_DIR, "init.sh")
PS1 = os.path.join(TEMPLATE_DIR, "init.ps1")


def write(path, text, newline=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline=newline) as fh:
        fh.write(text)


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


def run(project, pwsh, *args):
    cmd = ([pwsh, "-NoProfile", "-File", PS1] if pwsh else ["bash", SH]) + list(args)
    env = dict(os.environ, TEMPLATE_DIR=TEMPLATE_DIR)
    return subprocess.run(cmd, cwd=project, env=env, capture_output=True, encoding="utf-8", errors="replace",
                          stdin=subprocess.DEVNULL)


def case_user_files_never_overwritten(project, pwsh):
    mine = {"CLAUDE.md": "# my project\n", "CHANGELOG.md": "# my log\n",
            "docs/backend.md": "# my backend\n", ".claude/settings.json": '{"permissions": {}}\n'}
    for rel, text in mine.items():
        write(os.path.join(project, rel), text)
    for args in ((), ("--update",)):
        proc = run(project, pwsh, *args)
        if proc.returncode != 0:
            return f"init {' '.join(args)} exited {proc.returncode}: {proc.stderr[-300:]}"
    changed = [rel for rel, text in mine.items() if read(os.path.join(project, rel)) != text.encode()]
    if changed:
        return f"user files overwritten: {changed}"
    if not os.path.exists(os.path.join(project, "docs", "conventions.md")):
        return "a missing docs/ file was not seeded next to the user's own"
    return None


def case_fresh_project_is_seeded(project, pwsh):
    if run(project, pwsh).returncode != 0:
        return "init exited non-zero"
    missing = [rel for rel in ("CLAUDE.md", "CHANGELOG.md", ".gitignore", "docs/conventions.md",
                               ".claude/settings.json", ".claude/settings.local.json.example")
               if not os.path.exists(os.path.join(project, rel))]
    return f"not seeded: {missing}" if missing else None


def case_gitignore_merge(project, pwsh):
    # No final newline, a user comment and a negation that must stay behind
    # its parent: sorting hoisted `!keep.log` above `*.log`.
    gi = os.path.join(project, ".gitignore")
    write(gi, "# mine\n*.log\n!keep.log\nbuild.log")
    for _ in range(2):
        if run(project, pwsh).returncode != 0:
            return "init exited non-zero"
    lines = read(gi).decode().splitlines()
    if lines[:4] != ["# mine", "*.log", "!keep.log", "build.log"]:
        return f"the user's lines were changed or glued: {lines[:5]}"
    dupes = sorted({ln for ln in lines if ln and lines.count(ln) > 1})
    return f"lines appended twice: {dupes}" if dupes else None


def case_gitignore_crlf(project, pwsh):
    gi = os.path.join(project, ".gitignore")
    write(gi, "node_modules/\r\n.env\r\n", newline="")
    for _ in range(2):
        if run(project, pwsh).returncode != 0:
            return "init exited non-zero"
    lines = read(gi).decode().replace("\r", "").splitlines()
    dupes = sorted({ln for ln in lines if ln and lines.count(ln) > 1})
    return f"CRLF lines were not recognised, appended again: {dupes}" if dupes else None


def case_recursive_flags_alone_deploy_nothing(project, pwsh):
    for flag in ("--dry-run", "--yes", "--depth=2"):
        proc = run(project, pwsh, "--update", flag)
        if proc.returncode != 9:
            return f"`init --update {flag}` exited {proc.returncode}, want 9"
        if os.listdir(project):
            return f"`init --update {flag}` wrote {os.listdir(project)} — a dry run must not deploy"
    return None


def case_symlinks_are_not_written_through(project, pwsh):
    outside = tempfile.mkdtemp(prefix="init-outside-")
    try:
        target = os.path.join(outside, "rcfile")
        write(target, "export X=1\n")
        try:
            os.symlink(target, os.path.join(project, ".gitignore"))
            os.symlink(os.path.join(outside, "missing.md"), os.path.join(project, "CLAUDE.md"))
        except OSError:            # Windows without Developer Mode cannot create one
            return None
        proc = run(project, pwsh)
        if proc.returncode != 0:
            return f"init exited {proc.returncode} on a dangling symlink: {proc.stderr[-200:]}"
        if read(target) != b"export X=1\n":
            return "init wrote through a symlinked .gitignore into a file outside the project"
        if os.path.exists(os.path.join(outside, "missing.md")):
            return "init created a file outside the project through a dangling CLAUDE.md link"
    finally:
        shutil.rmtree(outside, ignore_errors=True)
    return None


def case_crlf_example_is_not_drift(project, pwsh):
    # The same text with CRLF line endings (a Windows checkout) is no edit.
    with open(os.path.join(TEMPLATE_DIR, ".claude", "settings.local.json.example"), encoding="utf-8", newline="") as fh:
        text = fh.read().replace("\r\n", "\n").replace("\n", "\r\n")
    write(os.path.join(project, ".claude", "settings.local.json.example"), text, newline="")
    proc = run(project, pwsh, "--update")
    if proc.returncode != 0:
        return "init exited non-zero"
    return "a CRLF copy of the example was reported as drift" if "DRIFT:" in proc.stderr else None


def case_edited_example_is_kept(project, pwsh):
    example = os.path.join(project, ".claude", "settings.local.json.example")
    write(example, '{"mine": true}\n')
    proc = run(project, pwsh, "--update")
    if proc.returncode != 0:
        return "init exited non-zero"
    if read(example) != b'{"mine": true}\n':
        return "an edited settings.local.json.example was overwritten"
    return None if "DRIFT:" in proc.stderr else "the drift was not reported"


def case_permissions_merge_keeps_user_rules(project, pwsh):
    settings = os.path.join(project, ".claude", "settings.json")
    write(settings, json.dumps({"permissions": {"allow": ["Bash(make:*)"], "deny": ["Read(./x)"]}}))
    stub = os.path.join(project, "bin")
    stubs.write_stub(stub, "codebase-memory-mcp")
    env_path = stub + os.pathsep + os.environ["PATH"]
    cmd = ([pwsh, "-NoProfile", "-File", PS1] if pwsh else ["bash", SH]) + ["--codebase-memory"]
    proc = subprocess.run(cmd, cwd=project, capture_output=True, encoding="utf-8", errors="replace",
                          env=dict(os.environ, TEMPLATE_DIR=TEMPLATE_DIR, PATH=env_path))
    if proc.returncode != 0:
        return f"init --codebase-memory exited {proc.returncode}: {proc.stderr[-200:]}"
    with open(settings, encoding="utf-8") as fh:
        perms = json.load(fh)["permissions"]
    if perms["allow"][:1] != ["Bash(make:*)"] or perms.get("deny") != ["Read(./x)"]:
        return f"the user's own rules were reordered or dropped: {perms}"
    if not any(r.startswith("mcp__codebase-memory-mcp__") for r in perms["allow"]):
        return "the read-only tool permissions were not added"
    write(settings, "{not json")
    cmd_again = subprocess.run(cmd, cwd=project, capture_output=True, encoding="utf-8", errors="replace",
                               env=dict(os.environ, TEMPLATE_DIR=TEMPLATE_DIR, PATH=env_path))
    if cmd_again.returncode != 0 or read(settings) != b"{not json":
        return "an unreadable settings.json was overwritten (or broke the deploy)"
    return None


def case_scaffolds(project, pwsh):
    deploy = "deploy.ps1" if pwsh else "deploy.sh"
    expected = {".env.example": "env.example.template", "Dockerfile": "Dockerfile.node",
                ".dockerignore": "dockerignore.template", "docker-compose.yml": "docker-compose.yml.template",
                "Caddyfile": "Caddyfile.template", deploy: deploy + ".template"}
    flags = ("--fullstack", "--runtime=node", "--compose", "--proxy=caddy", "--deploy-script")
    if run(project, pwsh, *flags).returncode != 0:
        return "init with every scaffold flag exited non-zero"
    for rel, src in expected.items():
        if read(os.path.join(project, rel)) != read(os.path.join(TEMPLATE_DIR, "scaffolds", src)):
            return f"{rel} is not the {src} scaffold"
    for d in ("backend", "clients/web", "scripts"):
        if not os.path.isdir(os.path.join(project, d)):
            return f"--fullstack did not create {d}/"
    write(os.path.join(project, "Dockerfile"), "FROM mine\n")
    if run(project, pwsh, "--runtime=python").returncode != 0:
        return "re-run exited non-zero"
    if read(os.path.join(project, "Dockerfile")) != b"FROM mine\n":
        return "a scaffold overwrote the user's own Dockerfile"
    proc = run(project, pwsh, "--runtime=bogus")
    if proc.returncode != 0 or "bogus" not in proc.stderr + proc.stdout:
        return "an unknown --runtime must warn and still deploy"
    return None


def case_ui_permissions_are_named(project, pwsh):
    stub = os.path.join(project, "bin")
    stubs.write_stub(stub, "npx")
    cmd = ([pwsh, "-NoProfile", "-File", PS1] if pwsh else ["bash", SH]) + ["--ui"]
    proc = subprocess.run(cmd, cwd=project, capture_output=True, encoding="utf-8", errors="replace",
                          env=dict(os.environ, TEMPLATE_DIR=TEMPLATE_DIR,
                                   PATH=stub + os.pathsep + os.environ["PATH"]))
    if proc.returncode != 0:
        return f"init --ui exited {proc.returncode}: {proc.stderr[-200:]}"
    with open(os.path.join(project, ".claude", "settings.json"), encoding="utf-8") as fh:
        allow = json.load(fh).get("permissions", {}).get("allow", [])
    if "mcp__playwright__browser_navigate" not in allow:
        return f"--ui did not merge the browser tool permissions: {allow}"
    risky = [r for r in allow if r.endswith(("__*", "browser_evaluate", "browser_file_upload",
                                             "browser_run_code_unsafe"))]
    return f"--ui allowed tools that must stay on ask: {risky}" if risky else None


CASES = [
    ("a fresh project is seeded", case_fresh_project_is_seeded),
    ("--ui allows the safe browser tools by name only", case_ui_permissions_are_named),
    ("user files are never overwritten, missing ones are seeded", case_user_files_never_overwritten),
    (".gitignore merge keeps order, glues nothing, appends once", case_gitignore_merge),
    ("a CRLF .gitignore is merged once", case_gitignore_crlf),
    ("--dry-run/--yes/--depth without --recursive deploy nothing", case_recursive_flags_alone_deploy_nothing),
    ("symlinks in the project are not written through", case_symlinks_are_not_written_through),
    ("an edited settings.local.json.example is kept and reported", case_edited_example_is_kept),
    ("a CRLF copy of the example is not drift", case_crlf_example_is_not_drift),
    ("the permission merge keeps the user's rules", case_permissions_merge_keeps_user_rules),
    ("scaffolds land once and never overwrite", case_scaffolds),
]


def main():
    args = pyhook.cli()
    total = bad = 0
    for pwsh, label in stubs.shell_targets(args.pwsh):
        for name, fn in CASES:
            project = tempfile.mkdtemp(prefix="init-seed-")
            try:
                problem = fn(project, pwsh)
            finally:
                shutil.rmtree(project, ignore_errors=True)
            total += 1
            bad += bool(problem)
            print(f"  {'ok  ' if not problem else 'BAD '}[{label}] {name}" + (f" — {problem}" if problem else ""))
    return pyhook.finish("init-seed", bad, total, args.pwsh)


if __name__ == "__main__":
    sys.exit(main())
