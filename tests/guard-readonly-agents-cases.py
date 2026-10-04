#!/usr/bin/env python3
"""Behavioural contract for guard-readonly-agents.py.

Run:  python3 tests/guard-readonly-agents-cases.py
      python3 tests/guard-readonly-agents-cases.py --pwsh PATH   # PowerShell command form too

An agent whose definition disallows Write and Edit (researcher, code-reviewer,
debugger, db-inspector, or a project's own) may not write through the shell
either: no file writes outside the temp folder and the session scratchpad, no
state-changing git, no package installs. Every other caller — the main
thread, Explore, an agent that can edit — is never judged, and a false deny
there would break ordinary work, so those controls matter as much as the
catches.

The fixture keeps the project OUTSIDE the hook's temp folder (TMPDIR/TEMP/TMP
point at a sibling), since a project under temp would be writable by design.
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyhook  # noqa: E402

DENY, ALLOW = "deny", "allow"

AGENTS = {
    "researcher": "---\nname: researcher\ndescription: x\ndisallowedTools: Write, Edit, NotebookEdit\n---\nBody\n",
    "db-inspector": "---\nname: db-inspector\ndescription: x\ntools: Bash, Read\n"
                    "disallowedTools: Write, Edit, NotebookEdit\n---\n",
    "lister": "---\nname: lister\ndescription: x\ndisallowedTools:\n  - Write\n  - Edit\n---\n",
    "half": "---\nname: half\ndescription: x\ndisallowedTools: Write\n---\n",
    "builder": "---\nname: builder\ndescription: x\ntools: Bash, Read, Edit, Write\n---\n",
}
PROJECT_AGENTS = {
    "proj-reader": "---\nname: proj-reader\ndescription: x\ndisallowedTools: [Write, Edit]\n---\n",
}

# (agent_type or None for the main thread, command, expected, why)
CASES = [
    # --- file writes ---------------------------------------------------------
    ("researcher", "sed -i 's/a/b/' app.py",              DENY, "sed -i on a project file"),
    ("researcher", "echo x > app.py",                     DENY, "a redirect into the project"),
    ("researcher", "cat > notes.md <<'EOF'\nhi\nEOF",     DENY, "a heredoc written into the project"),
    ("researcher", "rm -f build/cache.json",              DENY, "deleting a project file"),
    ("researcher", "mv app.py app2.py",                   DENY, "renaming a project file"),
    ("researcher", "cp TMP/x.py app.py",                  DENY, "copying over a project file"),
    ("researcher", "touch HOME/elsewhere.txt",            DENY, "outside the project is not allowed either"),
    ("researcher", "echo x > TMP/probe.txt",              ALLOW, "the temp folder is scratch space"),
    ("researcher", "echo x > SCRATCH/notes.md",           ALLOW, "the session scratchpad is scratch space"),
    ("researcher", "cp app.py TMP/app.py",                ALLOW, "copying a project file into temp reads it"),
    ("researcher", "git status >/dev/null 2>&1",          ALLOW, "/dev/null and 2>&1 are not writes"),
    ("researcher", "npm test 2>&1 | tee TMP/log.txt",     ALLOW, "teeing a log into temp"),
    ("researcher", "cat app.py | head -5",                ALLOW, "reading"),
    ("researcher", "grep -rn TODO .",                     ALLOW, "searching"),
    ("researcher", "python3 TMP/repro.py",                ALLOW, "running a scratch script"),
    ("researcher", "cd TMP && echo x > probe.txt",        ALLOW, "a relative write after cd into temp"),
    ("researcher", "cd TMP && echo x > PROJECT/app.py",   DENY, "an absolute project path after cd into temp"),
    # --- git ---------------------------------------------------------------
    ("researcher", "git log --oneline -5",                ALLOW, "history"),
    ("researcher", "git diff HEAD",                       ALLOW, "diff"),
    ("researcher", "git -C . show HEAD~1",                ALLOW, "show through -C"),
    ("researcher", "git branch --show-current",           ALLOW, "listing a branch"),
    ("researcher", "git branch -a",                       ALLOW, "listing branches"),
    ("researcher", "git stash list",                      ALLOW, "listing stashes"),
    ("researcher", "git config --get user.name",          ALLOW, "reading config"),
    ("researcher", "git tag -l 'v1*'",                    ALLOW, "listing tags by pattern"),
    ("researcher", "git tag v2.0",                        DENY, "creating a tag"),
    ("researcher", "git checkout main",                   DENY, "switching the working tree"),
    ("researcher", "git -C . stash",                      DENY, "stashing through -C"),
    ("researcher", "git commit -m x",                     DENY, "committing"),
    ("researcher", "git add -A",                          DENY, "staging"),
    ("researcher", "git branch feature/x",                DENY, "creating a branch"),
    ("researcher", "git branch -D old",                   DENY, "deleting a branch"),
    ("researcher", "git config user.name x",              DENY, "writing config"),
    ("researcher", "git fetch origin",                    ALLOW, "fetch updates remote-tracking refs, not the working tree"),
    ("researcher", "git fetch --prune",                   ALLOW, "pruning remote-tracking refs"),
    ("researcher", "git fetch origin main:main",          DENY, "a refspec with a destination writes a local branch"),
    ("researcher", "git fetch origin +refs/heads/x:refs/heads/x", DENY, "a forced local-branch refspec"),
    ("researcher", "git pull",                            DENY, "pulling"),
    # --- installs ----------------------------------------------------------
    ("researcher", "npm install left-pad",                DENY, "an npm install"),
    ("researcher", "npm ci",                              DENY, "npm ci rewrites node_modules"),
    ("researcher", "pip install requests",                DENY, "a pip install"),
    ("researcher", "uv add httpx",                        DENY, "uv add"),
    ("researcher", "cargo add serde",                     DENY, "cargo add"),
    ("researcher", "npm test",                            ALLOW, "running tests"),
    ("researcher", "npm ls",                              ALLOW, "listing packages"),
    # --- which callers are judged --------------------------------------------
    (None,           "sed -i 's/a/b/' app.py",            ALLOW, "the main thread is never judged"),
    ("Explore",      "echo x > app.py",                   ALLOW, "a built-in agent has no definition file"),
    ("builder",      "echo x > app.py",                   ALLOW, "an agent that may Write and Edit"),
    ("half",         "echo x > app.py",                   ALLOW, "disallowing only Write is not read-only"),
    ("db-inspector", "echo x > app.py",                   DENY, "a tools: list without Write or Edit"),
    ("db-inspector", "sqlite3 app.db 'select 1'",         ALLOW, "SQL is not parsed here"),
    ("lister",       "git commit -m x",                   DENY, "a YAML-list disallowedTools"),
    ("proj-reader",  "echo x > app.py",                   DENY, "a project-level read-only agent"),
    ("plugin:rev",   "echo x > app.py",                   ALLOW, "a plugin agent's definition cannot be located"),
    ("researcher",   "echo 'unbalanced > app.py",          DENY, "unparseable quoting from a read-only agent fails closed"),
]

POWERSHELL = [
    ("researcher", "Set-Content app.py x",               DENY, "Set-Content into the project"),
    ("researcher", "Set-Content -Path TMP/x.txt -Value hi", ALLOW, "Set-Content into temp"),
    ("researcher", "Remove-Item app.py",                 DENY, "Remove-Item a project file"),
    ("researcher", "Get-ChildItem > $null",              ALLOW, "$null is not a write"),
    ("researcher", "Get-Content app.py",                 ALLOW, "reading"),
]


def build():
    base = tempfile.mkdtemp(prefix="readonly-agents-")
    home, project, hooktmp, scratch = (os.path.join(base, d) for d in ("home", "project", "hooktmp", "scratch"))
    for d in (os.path.join(home, ".claude", "agents"), os.path.join(project, ".claude", "agents"), hooktmp, scratch):
        os.makedirs(d)
    for name, text in AGENTS.items():
        with open(os.path.join(home, ".claude", "agents", f"{name}.md"), "w", encoding="utf-8") as fh:
            fh.write(text)
    with open(os.path.join(project, ".claude", "agents", "proj-reader.md"), "w", encoding="utf-8") as fh:
        fh.write(PROJECT_AGENTS["proj-reader"])
    with open(os.path.join(project, "app.py"), "w") as fh:
        fh.write("x = 1\n")
    return base, home, project, hooktmp, scratch


def expand(command, home, project, hooktmp, scratch):
    for token, path in (("SCRATCH", scratch), ("PROJECT", project), ("HOME", home), ("TMP", hooktmp)):
        command = command.replace(token, path.replace("\\", "/"))
    return command


def decide(runner, agent, command, tool, dirs):
    base, home, project, hooktmp, scratch = dirs
    payload = pyhook.payload(tool, {"command": expand(command, home, project, hooktmp, scratch)},
                             cwd=project, scratchpad_dir=scratch)
    if agent:
        payload.update(agent_id="a1", agent_type=agent)
    env = dict(pyhook.home_env(home), TMPDIR=hooktmp, TEMP=hooktmp, TMP=hooktmp)
    code, out, err = pyhook.run("guard-readonly-agents", payload, cwd=project, env=env, pwsh=runner)
    return pyhook.verdict(code, out, err)


def main():
    args = pyhook.cli()

    dirs = build()
    failures = 0
    try:
        for tool, cases in (("Bash", CASES), ("PowerShell", POWERSHELL)):
            for agent, command, want, why in cases:
                for name, runner in pyhook.runners(args.pwsh):
                    got = decide(runner, agent, command, tool, dirs)
                    if got != want:
                        failures += 1
                        print(f"  FAIL [{name}/{tool}] want {want} got {got} | {agent}: {command!r}   ({why})")
    finally:
        shutil.rmtree(dirs[0], ignore_errors=True)

    return pyhook.finish("guard-readonly-agents", failures, len(CASES) + len(POWERSHELL), args.pwsh)


if __name__ == "__main__":
    sys.exit(main())
