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
- Linux / macOS / WSL: bash and `python3` (most hooks are Python; the rest parse their JSON input with it)
- Windows: PowerShell 5.1+ and Python 3 (the installer stops if it finds no working interpreter)

## What gets installed

`install.sh` copies the central config into `~/.claude/`:

- **Hooks** — deterministic guarantees that run on every tool call: block destructive commands and remote-code-execution patterns (`guard-destructive`), block force pushes and direct pushes to main (`guard-push-main`), catch secrets before they land in a commit (`detect-secrets`), flag new code comments that cite a plan step or point into the project's docs (`comment-hygiene`), lint and typecheck files as they are edited (`verify-on-edit`), deny commit trailers, emoji and non-English commit messages and ask before `--amend` (`guard-commit`), ask before any new dependency (`guard-dependencies`), tell the model which code-intelligence tools a project has (`code-intel-context`, `explore-graph-prompt`), keep mirrored docs in sync, protect the installed config from in-project edits, re-inject a digest of the central rules after context compaction, and flag a turn that changed code without a CHANGELOG entry (`changelog-reminder`).
- **Agents** — `researcher` (architectural deep-dives), `code-reviewer` (skeptical post-change review), `debugger` (root-cause diagnosis), `db-inspector` (read-only SQL inspection).
- **Skills** — workflow commands available in every project: `/verify`, `/commit`, `/audit`, `/changes`, `/plan-feature`, `/resume-context`, `/update-docs`, `/compound`, `/implement-ui`, `/readme`.
- **Rules** — coding conventions: workflow and AI collaboration load in every session, code quality and security when a matching source file is read.
- **Base settings** — merged into your existing `~/.claude/settings.json`. Your personal keys (theme, model, env and so on) are kept, and defaults such as the output style are only added when absent. `permissions`, `hooks` and `attribution` belong to dotclaude and are replaced on every install; if yours held entries of their own, the previous file is saved as `settings.json.bak-<timestamp>` first. Put personal rules and hooks in a project's `.claude/settings.json` or `settings.local.json`, which merge on top.

Re-running the installer is safe and idempotent: it owns only the files it shipped, never your own skills, agents, or global CLAUDE.md.

## Per-project deploy

`/init-project` runs an interview (project type, framework, Docker, deployment, MCP servers, database), then prints a command like:

```bash
bash ~/.claude/templates/project/init.sh --lsp=typescript-lsp --ui
```

Running it deploys only the project-specific surface:

- `CLAUDE.md` and `CHANGELOG.md` starters with the interview answers filled in
- `docs/` — contract docs (backend, UI, user stories, conventions) maintained by `/update-docs`
- `.claude/settings.json` stub for project-level additions
- The official Claude Code LSP plugin for the project's language (`--lsp=<plugin>`, installed at project scope): symbol navigation and diagnostics after every edit
- `.mcp.json` composed from fragments: `--codebase-memory` adds a persistent code graph (codebase-memory-mcp), `--xcode` adds the Xcode server, `--ui` adds Playwright
- Optional infra scaffolds (Dockerfile, docker-compose, Caddyfile, deploy script, `.env.example`)

The hooks, agents, skills and rules are not copied into the project — they already apply from `~/.claude/`.

`/implement-ui` can research real design references before drawing a canvas when the [Refero](https://refero.design) MCP is connected. It needs a Refero subscription and is personal, so it is added once at user scope, never to a project's `.mcp.json`:

```bash
claude mcp add --scope user --transport http refero https://api.refero.design/mcp
```

`/init-project` offers this in its MCP interview the first time a UI project is set up on a machine and prints the line for you. `/implement-ui` asks each time whether to research first or design directly.

## Updating

```bash
git pull && ./install.sh
```

That refreshes the central config for every project at once. Inside a project, `/init-project --update` re-seeds any missing per-project files and offers new template additions without overwriting your edits.

To refresh every project under a folder in one go — for example after an update retires something projects were deployed with:

```bash
bash ~/.claude/templates/project/init.sh --update --recursive ~/projects --dry-run   # show the plan only
bash ~/.claude/templates/project/init.sh --update --recursive ~/projects             # show it, ask, then apply
```

It finds the projects dotclaude deployed (skipping dependency folders, nested projects and template copies), re-runs the deploy in each with the flags its `.mcp.json` implies, prunes hooks and MCP servers that are no longer shipped, and lists — never deletes — leftover directories such as `.serena/`. `--yes` skips the confirmation. `init.ps1` takes the same flags.

## Notes on the safety hooks

Direct pushes to `main`/`master` are blocked by default; for solo repos, opt out with `"allowPushToMain": true` in the project's `.claude/settings.local.json`. Force pushes stay blocked regardless. Destructive-command and secret-detection hooks have no opt-out.

## Development

Every hook is a single Python file in `global/.claude/hooks/` (the installers wire it for both Unix and Windows). The installers and the deployers ship as `.sh`/`.ps1` pairs that must stay logically equivalent — change both in the same commit. Before committing:

```bash
python3 check.py
```

It validates the pairs, the settings wiring, and the doc inventories. The safety hooks each have a case matrix under `tests/` (for example `python3 tests/guard-push-main-cases.py`); add `--pwsh <path>` to verify the PowerShell sibling agrees on every case. `DESIGN.md` records the rationale behind every structural decision — read the relevant section before changing architecture.
