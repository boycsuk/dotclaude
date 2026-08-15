# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`dotclaude` is the **source of truth** for a portable Claude Code setup. It does not produce a runtime artifact — it produces files that get copied into `~/.claude/` (the user's global Claude Code config) and from there into individual projects via the `/init-project` skill.

There is no build, no test suite, no linter. The "release" is `./install.sh` (or `install.ps1`) on a developer's machine, plus `git push`. Treat changes as if they were live config: a broken `settings.json` or hook script breaks every project that later runs `/init-project`.

## Layout — what lives where, and why

**Two-tier model (centralized core + per-project surface).** The reusable
artifacts — hooks, agents, skills, rules, output-styles — are CENTRAL: they
live in `global/.claude/`, `install.sh` copies them into `~/.claude/`, and the
harness applies them to every project automatically. Improving the master repo
and re-running `install.sh` propagates to all projects at once — no per-project
update. Only the project-specific surface (CLAUDE.md, docs/, a settings stub,
scaffolds) is deployed per project by `/init-project`. See DESIGN.md §23.

```
dotclaude/
├── install.sh / install.ps1     # bootstrap: installs global/.claude/ into ~/.claude/ (MERGES settings),
│                                # plus templates/project/ and skills/init-project/
├── CLAUDE.md                    # ← THIS FILE (project guide for Claude Code)
├── DESIGN.md                    # rationale for every architectural choice
├── README.md                    # human-facing install/usage doc
├── global/.claude/              # CENTRAL config — installed into ~/.claude/, applies to ALL projects
│   ├── settings.json            # base permissions + hooks + attribution (install resolves OS form)
│   ├── hooks/                   # .sh + .ps1 pairs — must stay in lockstep
│   ├── agents/                  # researcher, code-reviewer, debugger, db-inspector
│   ├── rules/                   # progressive-disclosure conventions
│   ├── skills/                  # workflow skills (verify, commit, audit, update-docs, …)
│   └── output-styles/           # opt-in tone/language conventions (dotclaude.md)
├── skills/init-project/         # the global deployer skill (also installed into ~/.claude/skills/)
│   └── SKILL.md
└── templates/project/           # the PER-PROJECT skeleton (deployed by /init-project)
    ├── init.sh / init.ps1       # internal deployer — copies only per-project files
    ├── CLAUDE.md.template       # per-project CLAUDE.md with {{placeholders}}
    ├── CHANGELOG.md.template    # Keep-a-Changelog starter
    ├── .gitignore.template
    ├── mcp/                     # one fragment per MCP server (serena, graphify, xcode, playwright);
    │                            # ./.mcp.json is COMPOSED from these, never copied
    ├── scaffolds/               # infra templates (Dockerfile, compose, deploy.sh, …)
    ├── docs/                    # portable contract docs (backend.md, ui.md, user-stories.md, conventions.md, README.md)
    └── .claude/
        ├── settings.json        # per-project STUB (base config is central; this only ADDS, e.g. MCP perms)
        ├── serena-hooks.json     # Serena drift-prevention hooks — MERGED into settings.json on --serena (not a standalone deployed file)
        └── settings.local.json.example  # personal overrides (gitignored once renamed)
```

**Two CLAUDE.md files exist intentionally.** This one (repo-level) tells Claude how to work *inside this repo*. `templates/project/CLAUDE.md.template` is the per-project file that gets deployed elsewhere. Don't confuse them.

## Critical architectural constraints

### 1. The skill plans, the user executes — do not merge them back

`skills/init-project/SKILL.md` deliberately does NOT run `init.sh` itself. It detects the stack, runs the interview, then **prints** the exact `bash …/init.sh [--serena]` command for the user to run from a normal terminal. After the user confirms `deploy OK`, the skill resumes with `Edit` to fill placeholders.

The temptation to "just run the script from the skill" via a `!`-prefixed shell block is real and was tried — it fails reliably for reasons that are not in our control:

- The permission matcher rejects compound shell constructs (`&&`, `||`, `>`, `2>`, pipes, multiple statements), `$HOME` expansion against binaries other than `bash`, and treats exit non-zero as a fatal skill abort. References: anthropics/claude-code #16561, #43713, #14956.
- Claude Code's progressive-disclosure loader reads `.claude/rules/*.md` into context while the skill runs. That races with the file copy and produces `cp: cannot create regular file …: File exists` against paths that were just `rm -rf`'d. Reference: #35096.
- An audit of every public scaffolding skill (anthropics/skills, vercel-labs/skills, etc.) confirmed none of them attempt in-skill file deployment — they all delegate to an external script the user runs.

If you're tempted to "fix" the skill so it runs `init.sh` automatically, **don't.** Read DESIGN.md §15 first. The split is intentional.

### 2. Bash and PowerShell hooks must stay logically equivalent

`global/.claude/hooks/` ships every hook twice: `foo.sh` and `foo.ps1`. `install.sh` strips `.ps1` on Unix and `install.ps1` strips `.sh` on Windows when installing into `~/.claude/`. **When you change one, change the other in the same commit.** Diverging silently breaks Windows users (no CI catches this).

Same rule for `install.sh` ↔ `install.ps1` and `templates/project/init.sh` ↔ `init.ps1`.

### 3. Re-running the installer must be idempotent and never touch user content

`install.sh` overwrites the central artifacts it owns (`~/.claude/{hooks,agents,skills,rules,output-styles}`, `templates/project/`, `skills/init-project/`) wholesale, and **merges** the base `settings.json` into `~/.claude/settings.json` preserving the user's own keys. It does **not** touch `~/.claude/CLAUDE.md` at all — the repo's `CLAUDE.md` is this repo's maintenance guide, not user global preferences, so it is never copied out. The user can `git pull && ./install.sh` repeatedly without losing global preferences.

If you change install behaviour, preserve this: the installer owns the central artifacts, merges settings non-destructively, and leaves everything else in `~/.claude/` (CLAUDE.md, projects/, credentials) untouched.

### 4. The template is a starting point, not a finished product

`templates/project/.claude/` ships a neutral skeleton. Stack-specific additions (deploy-vercel skills, Django agents, etc.) belong **in each project**, not here. The bar for adding something to `templates/project/` is: *every* future project would benefit. See DESIGN.md §3, §6, §13 for the reasoning.

When `/compound` (a skill inside the template) suggests promoting a project-local artifact to the global template, the workflow is:
1. Apply the change in `templates/project/.claude/` here.
2. Atomic commit describing what was learned.
3. `git push`. Other machines run `git pull && ./install.sh`.

## How the pieces fit together at runtime

1. **Bootstrap / propagation.** User runs `./install.sh` in a clone of this repo. It installs the central config — `global/.claude/{hooks,agents,skills,rules,output-styles}` and the base `settings.json` (MERGED into the user's, never clobbering their personal keys) — into `~/.claude/`, resolving the OS hook form (`.sh` on Unix, `.ps1` + PowerShell rules on Windows). It also copies `templates/project/` and `skills/init-project/` into `~/.claude/`. **Re-running `install.sh` after a master-repo change is how the improvement reaches every project at once** — the central artifacts apply to all projects via the harness.

2. **Per-project plan.** In any project, the user opens Claude Code and types `/init-project`. The skill (`skills/init-project/SKILL.md`):
   - **First-time projects only:** asks whether the user wants to describe the project up-front (SKILL.md §0). If yes, that description biases the recommended option in every subsequent question (project type, framework, Docker, deployment, MCPs, DB) — the questions and their answer sets stay the same, only the order and "(Recommended)" tag changes. If no, the interview runs neutrally. Skipped on re-runs (the description already lives in the project's CLAUDE.md). See DESIGN.md §16.
   - Detects platform (Linux/macOS/WSL → `sh`, Windows → `ps1`).
   - Detects stack from `package.json` / `pyproject.toml` / `Cargo.toml` / `go.mod` etc., or interviews via AskUserQuestion if empty.
   - Asks which MCPs to authorize (multiSelect).
   - Detects SQL stack for the `db-inspector` agent.
   - Prints the exact terminal command (`bash ~/.claude/templates/project/init.sh [--serena] [--xcode] [--ui]`) for the user to run.

3. **User executes.** From a normal terminal (not from inside Claude Code), the user runs the printed command. `init.sh` copies only the per-project files (CLAUDE.md, CHANGELOG.md, docs/, the settings.json stub, .gitignore), composes `.mcp.json` from the `mcp/` fragments the flags select (`--serena` → serena + graphify, `--xcode` → xcode, `--ui` → playwright), writes any requested scaffolds, and prints `init.sh: deploy OK`. The central hooks/agents/skills/rules/output-styles are NOT copied — they already live in `~/.claude/`. See decision 15 in DESIGN.md for why this is split from the skill.

4. **Per-project personalize.** The user returns to Claude Code and confirms. The skill resumes and fills `{{placeholders}}` in the deployed `CLAUDE.md` and `settings.json` using the `Edit` tool, then verifies the deploy.

5. **In the deployed project.** The hooks, agents, skills, rules, and output-styles come from `~/.claude/` (central) and apply automatically — they are NOT in the project. Claude Code merges the project's `.claude/settings.json` stub (MCP perms, project overrides) on top of the central `~/.claude/settings.json` (base permissions + hooks). The central hooks (verify-on-edit, guard-destructive, guard-push-main, detect-secrets, sync-mirror-docs, guard-central-config, reinject-rules) and permissions therefore apply in every project; `guard-push-main` blocks force push always and direct push to main/master unless `"allowPushToMain": true` is set in `.claude/settings.local.json` (see DESIGN.md §18). `guard-central-config` blocks editing the installed `~/.claude/` config from inside a project — edit the source in `global/.claude/` and re-run `./install.sh` (see §23).

6. **Re-runs.** To pick up master-repo improvements to the central artifacts, the user runs `git pull && ./install.sh` in the dotclaude clone — that updates `~/.claude/` for every project at once. `/init-project --update` inside a project only re-seeds missing per-project files and drift-reports `settings.local.json.example`; it no longer refreshes hooks/agents/skills/rules (those are central). The skill still offers new `CLAUDE.md.template` bullets for the user to opt into (§1d) and, for projects with Serena, reconciles missing Serena/Graphify improvements (§1e). See DESIGN.md §19, §23.

## When to update what

| You discovered… | Edit… |
|---|---|
| A bug in the deployer | `skills/init-project/SKILL.md` or `templates/project/init.sh` / `init.ps1` |
| A new always-on guarantee for every project | New hook in `global/.claude/hooks/` (both `.sh` and `.ps1`) + entry in `global/.claude/settings.json` (and the PowerShell mirror in `install.ps1`) |
| A reusable workflow every project should have | New skill in `global/.claude/skills/` |
| A convention all projects should follow | Add to the right file in `global/.claude/rules/` (and mirror in `templates/project/docs/conventions.md`) |
| A specialist agent useful everywhere | New agent in `global/.claude/agents/` |
| A reusable tone/output convention | New file in `global/.claude/output-styles/` (opt-in via `outputStyle`) |
| A new flag or behavior in the deploy step | `templates/project/init.sh` AND `init.ps1` (keep them in lockstep), then update `skills/init-project/SKILL.md` to mention the flag in the printed command |
| A new portable doc convention every project should seed | `templates/project/docs/` (the seed) + entry in `global/.claude/skills/update-docs/SKILL.md` (the maintainer) |
| A change to the `--update` re-deploy or drift-reconciliation flow | `templates/project/init.sh` AND `init.ps1` (in lockstep) + `skills/init-project/references/update-mode.md` §1b/§1c/§1d/§1e |
| Anything stack-specific | **Stop.** It probably belongs in the project, not the template |

## Non-obvious decisions worth re-reading

DESIGN.md captures the reasoning behind every structural choice — read it before any architecture-level change. The ones most likely to bite you if you skip it:

- §2: one neutral template + interview, not stack variants.
- §3: progressive disclosure via `rules/`. Keep `CLAUDE.md.template` under 200 lines.
- §5: hooks parse JSON via `python3 -c`, not `jq`. Don't reintroduce `jq`.
- §7: model selection — `inherit` everywhere except mechanical components (verify, changes, resume-context) which override to Haiku. `researcher` inherits (architectural synthesis is reasoning; quick lookups go to the built-in Explore agent). Do NOT downgrade reasoning-heavy agents. Reasoning agents (`researcher`, `debugger`, `code-reviewer`) also pin `effort: high` in frontmatter; `db-inspector` inherits both model and effort. **A skill's `model:` applies to the rest of the caller's turn unless it also sets `context: fork`** — that is why `verify` and `changes` fork (DESIGN.md §27).
- §9: Bash runs allow-by-default (`allow: ["Bash", …]`); the `deny` list + the `guard-destructive` hook (matches ALL Bash, blocks RCE/inline interpreters) are the safety net. `ask` still gates impactful ops (push, dep installs, chmod). Revised 2026-07-09 — see the §9 note before touching permissions.
- §10: hooks are deterministic guarantees, not advisory. If safety is non-negotiable, it goes in a hook, not in `CLAUDE.md`.
- §13: Serena is opt-in (`--serena` flag), not default. Reason: requires `uv tool install` as a host prerequisite that the template cannot guarantee. `--serena` also merges Serena's drift-prevention hooks (`serena-hooks.json`) into the project `settings.json` — the *deterministic* layer that keeps the model preferring Serena's tools over Grep/Edit (advisory prose alone decays under compaction). Hooks live in the project stub (not central) because they invoke the `serena-hooks` binary, which only exists where Serena was installed.
- §14: `db-inspector` is an agent (not a skill, not only the MCP) and is read-only by allow/denylist enforced in its prompt.
- §17: portable `docs/` seeded for every project (backend.md + ui.md + user-stories.md + conventions.md + README.md) and maintained via `/update-docs`; each doc is self-maintained for editors without skills. `conventions.md` is the repo-versioned copy of the coding conventions — present in every clone, unlike the personal `~/.claude/rules/` — so non-Claude-Code tools follow the same conventions. Coverage-over-depth: every capability listed, even briefly.
- §18: `guard-push-main` is opt-out via `"allowPushToMain": true` in `.claude/settings.local.json` (gitignored). Force push stays blocked regardless.
- §19/§23: after centralization (§23), `init.sh --update` only seeds missing per-project files and drift-reports `settings.local.json.example`; the old three-class hook/agent/skill/rule refresh is gone (those update via `git pull && ./install.sh`). `/init-project` still diffs CLAUDE.md bullets for non-destructive reconciliation.

## Operating in this repo

- **Run `python3 check.py` before every commit.** It is the closest thing this repo has to a test suite: twelve checks over the duplications the architecture requires (`.sh`/`.ps1` pairs, `install.ps1` deriving its rules from `settings.json`, doc inventories, shared extension globs, no inline interpreters in skills, hook wiring — no `if` gates and advisory hooks still emitting `additionalContext` — the safety-hook matrices and their known-bypass cases, DESIGN.md's structural headings, JSON validity). It exists because prose asking for lockstep did not hold — four of five spot-checked duplications had already diverged. See DESIGN.md §25.
- **After touching a safety hook, run its case matrix** — `tests/guard-push-main-cases.py` (61 cases), `tests/guard-destructive-cases.py` (48), `tests/detect-secrets-cases.py` (39), `tests/guard-central-config-cases.py` (17), `tests/verify-on-edit-cases.py` (11). Add `--pwsh <path>` to verify the PowerShell sibling agrees on every case. Every one of these hooks shipped defects that reading them did not reveal, so a newly discovered case goes in the matrix *before* the fix. See DESIGN.md §18, §26 and §27.
- **After touching a deployer or installer, run their matrices** — `tests/mcp-merge-cases.py` (composition, prerequisite exit codes, the serena-hooks settings merge) and `tests/install-cases.py` (settings merge preserves personal keys, manifest add/remove cycle, unparseable-settings backup). Both take `--pwsh <path>`.
- **Hook entries in `settings.json` carry no `if:` gates, on purpose.** An `if` pattern is prefix-anchored, so it reopens exactly the wrapped-form bypasses the hooks' own parsers close (`"if": "Bash(git push *)"` let `git -C /repo push origin main` through unjudged, while the matrix passed because it invokes the hook directly). Every hook self-gates and exits 0 fast on non-matches. DESIGN.md §27(b).
- **An advisory hook must deliver through `hookSpecificOutput.additionalContext` on stdout, never stderr.** With exit 0, stderr goes to the debug log only — three hooks were inert for months that way. DESIGN.md §17 (2026-08-15 revision).
- **After touching `check.py`, run `bash tests/check-selftest.sh`** — it injects each regression check.py claims to catch and asserts it fails, plus a control run on a pristine copy. A validator nobody tests passes on a broken repo: this one shipped blind to every central skill (a `glob("**/*.md")` that silently skips dot-directories) and the self-test is what found it.
- Beyond that, validation is manual: after editing `init.sh`, dry-run it in a throwaway directory.
- **To test the PowerShell side on Linux**, download the portable tarball (`powershell-<v>-linux-x64.tar.gz` from the PowerShell releases) and run `HOME=/tmp/fakehome pwsh -NoProfile -File install.ps1`. Note `$HOME` is **read-only inside** a PowerShell session — isolating it by assigning `$HOME` in the script does not work and will write to your real `~/.claude`; set the `HOME` env var in the *parent* process instead. (If you do clobber it, `bash ./install.sh` restores everything; personal keys in `settings.json` survive either way.)
- **Parse-checking a `.ps1` proves nothing about whether it runs.** A syntax pass over all twelve `.ps1` files reported clean while `guard-push-main.ps1` was dead on arrival: `return if (...) {...}` is a runtime error, and PowerShell unwraps a one-element array slice into a bare string (so `$rest[0]` is its first *character*, and `git push` was never recognised as a push). Always pipe real hook input through the `.ps1` and check both the exit code and stderr — `tests/guard-push-main-cases.py --pwsh` does exactly that. Wrap every array slice in `@(...)`.
- Commits are atomic per concern (one fix, one decision). Commit messages follow the existing log style — terse, imperative, scope-prefixed (`fix(init-project): …`).
- The repo enforces a project-wide rule (also in user memory): **never add `Co-Authored-By` or any AI signature trailer to commits.** Don't add one even if a tool defaults to it.
