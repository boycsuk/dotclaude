# dotclaude

A portable Claude Code setup in one repo. It installs a shared core of hooks, agents, skills and rules into `~/.claude/` — applied automatically to every project on the machine — and deploys a thin per-project skeleton (CLAUDE.md, docs, settings stub) with a single command.

Claude Code config tends to drift: each machine accumulates its own hooks, each project its own conventions, and improvements never travel. This repo is the source of truth instead. Fix something here, re-run the installer, and every project on every machine picks it up.

## Quickstart

```bash
git clone https://github.com/boycsuk/dotclaude.git
cd dotclaude
./install.sh
```

On Windows, run `install.ps1` from PowerShell instead.

Then open Claude Code in any project and run `/init-project`. It detects the stack, asks a few questions, and prints the exact deploy command to run in your terminal.

## Requirements

- Claude Code
- Linux / macOS / WSL: bash and `python3` (the hooks parse their JSON input with it)
- Windows: PowerShell

## What gets installed

`install.sh` copies the central config into `~/.claude/`:

- **Hooks** — deterministic guarantees that run on every tool call: block destructive commands and remote-code-execution patterns (`guard-destructive`), block force pushes and direct pushes to main (`guard-push-main`), catch secrets before they land in a commit (`detect-secrets`), lint and typecheck files as they are edited (`verify-on-edit`), keep mirrored docs in sync, protect the installed config from in-project edits, and re-inject project rules lost to context compaction.
- **Agents** — `researcher` (architectural deep-dives), `code-reviewer` (skeptical post-change review), `debugger` (root-cause diagnosis), `db-inspector` (read-only SQL inspection).
- **Skills** — workflow commands available in every project: `/verify`, `/commit`, `/audit`, `/changes`, `/plan-feature`, `/resume-context`, `/update-docs`, `/compound`, `/implement-ui`, `/readme`.
- **Rules** — coding conventions loaded into every session (workflow, code quality, security, AI collaboration).
- **Base settings** — permissions and hook wiring, merged into your existing `~/.claude/settings.json` without touching your personal keys (theme, model, and so on).

Re-running the installer is safe and idempotent: it owns only the files it shipped, never your own skills, agents, or global CLAUDE.md.

## Per-project deploy

`/init-project` runs an interview (project type, framework, Docker, deployment, MCP servers, database), then prints a command like:

```bash
bash ~/.claude/templates/project/init.sh --serena
```

Running it deploys only the project-specific surface:

- `CLAUDE.md` and `CHANGELOG.md` starters with the interview answers filled in
- `docs/` — contract docs (backend, UI, user stories, conventions) maintained by `/update-docs`
- `.claude/settings.json` stub for project-level additions
- `.mcp.json` composed from fragments: `--serena` adds Serena and Graphify, `--xcode` adds the Xcode server, `--ui` adds Playwright
- Optional infra scaffolds (Dockerfile, docker-compose, Caddyfile, deploy script, `.env.example`)

The hooks, agents, skills and rules are not copied into the project — they already apply from `~/.claude/`.

## Updating

```bash
git pull && ./install.sh
```

That refreshes the central config for every project at once. Inside a project, `/init-project --update` re-seeds any missing per-project files and offers new template additions without overwriting your edits.

## Notes on the safety hooks

Direct pushes to `main`/`master` are blocked by default; for solo repos, opt out with `"allowPushToMain": true` in the project's `.claude/settings.local.json`. Force pushes stay blocked regardless. Destructive-command and secret-detection hooks have no opt-out.

## Development

Hooks, installers and deployers ship as `.sh`/`.ps1` pairs that must stay logically equivalent — change both in the same commit. Before committing:

```bash
python3 check.py
```

It validates the pairs, the settings wiring, and the doc inventories. The safety hooks each have a case matrix under `tests/` (for example `python3 tests/guard-push-main-cases.py`); add `--pwsh <path>` to verify the PowerShell sibling agrees on every case. `DESIGN.md` records the rationale behind every structural decision — read the relevant section before changing architecture.
