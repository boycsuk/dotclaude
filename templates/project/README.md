# Claude Code project template

The PER-PROJECT half of the dotclaude setup, deployed with `/init-project`. The
reusable core (hooks, agents, skills, rules, output-styles) is NOT here — it is
central in `~/.claude/` (installed from the dotclaude repo's `global/.claude/`)
and applies to every project automatically. See DESIGN.md §23.

## What `/init-project` deploys (per-project only)

```
<project root>/
├── CLAUDE.md              # WHAT/WHY/HOW + compaction guidance
├── CHANGELOG.md           # Keep a Changelog format
├── .gitignore             # Excludes settings.local.json and secrets
├── docs/                  # Portable contract surface (travels with the repo)
│   ├── README.md                # The convention + coverage-over-depth rule
│   ├── backend.md               # API contract: endpoints, request/response shapes, auth, error model
│   ├── user-stories.md          # Behavioral contract: what the user can do (platform-agnostic)
│   └── conventions.md           # How to write the code — portable mirror of the central rules for non-Claude-Code tools
├── .mcp.json              # Only when MCP flags were passed — COMPOSED per server (--xcode, --ui → playwright, --codebase-memory); hand-added servers survive
└── .claude/
    ├── settings.json            # Per-project STUB — only adds project-specific perms (MCP, etc.); base config is central
    └── settings.local.json.example   # Personal overrides; rename to settings.local.json
```

## The central core (in `~/.claude/`, shared by every project)

Installed from the dotclaude repo (`global/.claude/`) via `install.sh`; updated
for all projects at once with `git pull && ./install.sh`:

- **hooks/** — verify-on-edit, guard-destructive, guard-push-main, guard-commit (denies attribution trailers, emoji and non-English commit messages; asks before `--amend`, commits on main, a commit without its CHANGELOG entry, a `.sh`/`.ps1` pair committed half, and a commit that includes a secret-bearing file or adds a literal secret, named by file, line and kind, never by value), guard-dependencies (asks before any command or manifest edit that adds a dependency, naming unpinned versions and the audit command), guard-readonly-agents (an agent whose definition gives it no Write or Edit — researcher, code-reviewer, debugger, db-inspector, or a project's own — may not write files outside temp, change git state or install packages through the shell either), detect-secrets, comment-hygiene (tells Claude to rewrite a new code comment that cites a plan step or points into the project's docs, such as "see CLAUDE.md" — advisory, never blocks), sync-mirror-docs, design-sync (after an edit to a file a `docs/design/` spec names on its `Code:` line, reminds Claude to keep that spec, and the canvas when there is one, in step — advisory, never blocks), guard-central-config (blocks editing the central `~/.claude/` config from inside a project), reinject-rules (re-primes the non-negotiable conventions after a context compaction), code-intel-context (tells the session and every code-reading subagent which code-intelligence tools the project has — the LSP plugin, the codebase-memory graph — and when to use each; silent where there are none), explore-graph-prompt (appends the same guidance to every Explore delegation, since Explore skips CLAUDE.md), changelog-reminder (says so when a turn ends with code changed and CHANGELOG.md untouched — advisory, never blocks).
- **agents/** — researcher, code-reviewer, debugger, db-inspector.
- **skills/** — verify, commit, changes, plan-feature, compound, resume-context, update-docs, audit, readme, implement-ui (no design yet → a Design canvas with parameterised components, optionally researched first in the Refero MCP; design reference → the project's `docs/design/` folder (tokens, a status index, one spec per component and screen; created on first use, never seeded) → section-by-section build with a screenshot-vs-reference loop; pairs with the playwright MCP deployed by `init.sh --ui`).
- **rules/** — code-quality, security, workflow, ai-collaboration.
- **output-styles/** — dotclaude (tone/language conventions; `install.sh` sets `outputStyle` to it unless you chose another style).
- **settings.json** — base permissions + hooks + attribution (merged into your `~/.claude/settings.json`).

A project can only ADD to these (its own `.claude/rules/x.md`, an extra agent); it cannot edit or disable the central ones.

## How to deploy

Deployment is split in two phases: the `/init-project` skill plans and personalizes, you run the actual copy from a terminal.

**1. Plan with Claude Code.** In any project (empty or existing), open Claude Code and run:

```
/init-project
```

The skill detects your OS, detects your stack (or interviews you), and asks which MCP servers to authorize. At the end it prints the exact command for you to run.

**2. Execute in a terminal.** Copy the command the skill gave you and run it in your normal shell (not from inside Claude Code). It looks like:

```bash
cd <your project>
bash ~/.claude/templates/project/init.sh [--lsp=<plugin>] [--codebase-memory] [--xcode] [--ui] [scaffold flags]
```

`--lsp=<plugin>` installs the official Claude Code LSP plugin for the project's language at project scope (see below). The MCP flags are added by the skill per the interview: `--codebase-memory` (persistent code graph; needs the `codebase-memory-mcp` binary), `--xcode` (Apple's `xcrun mcpbridge`, macOS + Xcode 26.3+ only), `--ui` (Playwright browser MCP — lets the model screenshot the running app, which `/implement-ui` uses to verify UI work against a design reference; needs `npx`). Scaffold flags (`--fullstack`, `--runtime=`, `--compose`, `--proxy=`, `--deploy-script`) per the interview. When the script prints `init.sh: deploy OK`, return to Claude Code.

**3. Personalize with Claude Code.** The skill resumes: it fills in the placeholders in the deployed `CLAUDE.md` and `docs/conventions.md`, adds project-specific permissions to the `settings.json` stub, sanity-checks `.gitignore`, and verifies the deploy.

### Why the split

Skills that try to copy files into `.claude/` via shell blocks hit two reliability issues. The permission matcher rejects most shell constructs (compound commands, variable expansion against non-`bash` binaries, exit-non-zero) as documented in anthropics/claude-code issues #16561, #43713, #14956. Worse, Claude Code's rule-loading mechanism touches `.claude/rules/*.md` while the skill runs, racing with the file copy (#35096). Every public scaffolding skill avoids in-skill deployment for the same reason — the skill describes intent, the user executes. We follow that pattern.

### Re-deploying: drift report and bullet reconciliation

The reusable core (hooks, agents, skills, rules, output-styles) is central, so to pick up master-repo improvements **in every project at once**, run `git pull && ./install.sh` in the dotclaude clone — nothing per project.

Re-running `/init-project --update` inside a project only touches the per-project surface: it seeds missing files (CLAUDE.md, docs/, the settings stub) and drift-reports `settings.local.json.example` if you edited it. `CLAUDE.md`, `CHANGELOG.md`, and `docs/*` are never overwritten. After the deploy, `/init-project` runs **CLAUDE.md bullet reconciliation**: it compares your `CLAUDE.md` against `CLAUDE.md.template` per section and offers any new bullets via `AskUserQuestion` multiSelect — you pick which to add, nothing is overwritten without consent. See DESIGN.md §19, §23.

## How to extend

The reusable core is central, so **where** you add something depends on whether it should apply everywhere or only to this project:

**Reusable across all your projects → add it to the dotclaude repo (`global/.claude/`), then `git pull && ./install.sh`:**

| You want to add... | How |
|---|---|
| A repeatable workflow (deploy, test gen, etc.) | New skill in the repo's `global/.claude/skills/<name>/SKILL.md` |
| A non-negotiable guarantee (must always pass) | New hook `global/.claude/hooks/<name>.py` (with a `# hook-kind:` line) + its entry in `global/.claude/settings.json` + a `tests/<name>-cases.py` matrix |
| A specialist agent useful everywhere | New agent in the repo's `global/.claude/agents/<name>.md` |
| A convention all projects should follow | New file in the repo's `global/.claude/rules/<topic>.md` (mirror it in `templates/project/docs/conventions.md`) |

> Editing the installed `~/.claude/` copy from inside a project is blocked by the `guard-central-config` hook — change the source in the repo and re-install.

**Specific to THIS project only → add it in the project's own `.claude/` (it ADDS to the central config, never replaces it):**

| You want to add... | How |
|---|---|
| A project-only convention | Edit `CLAUDE.md` (Don't / Conventions), or create `.claude/rules/<topic>.md` for extensive ones |
| A project-only skill/agent | Create `.claude/skills/<name>/SKILL.md` or `.claude/agents/<name>.md` (lives only here) |
| Permissions for a new MCP, or a project-only override | Add to `permissions.allow` in the project's `.claude/settings.json` stub |
| A new high-level area doc (e.g. `mobile.md`, `bot.md`) | Add the file under `docs/`; `/update-docs` keeps it in sync with the diff |

## Code intelligence: the LSP plugin (`--lsp=<plugin>`)

`/init-project` maps the project's language to one of Claude Code's 13 official LSP plugins (`lsp-plugins.json`: pyright-lsp, typescript-lsp, gopls-lsp, rust-analyzer-lsp, …) and passes `--lsp=<plugin>`. The deploy runs `claude plugin install <plugin>@claude-plugins-official --scope project`, which records it in `.claude/settings.json`. The model then gets a read-only `LSP` tool (definitions, references, hover types, call hierarchy) and the language server's diagnostics after every edit ("Found N new diagnostic issues").

The plugin is only the wiring: the language-server binary (`pyright-langserver`, `typescript-language-server`, …) must be on PATH — the deploy warns with the install command if it is not. A teammate who clones the project runs the same `claude plugin install … --scope project` once: a plugin listed in `enabledPlugins` but not installed stays off. Languages without an official plugin (Bash, PowerShell, …) get none.

## Optional code graph: codebase-memory-mcp (`--codebase-memory`)

[codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) keeps a persistent graph of the code for structural questions: who calls X, what the current diff affects, dead code, architecture. The flag merges the server into `.mcp.json` and its 13 read-only tools into `permissions.allow` by exact name; the tools that write or delete the index stay on ask. Index it once after the deploy (`index_repository`); the server re-indexes on git changes after that. The index lives in `~/.cache/codebase-memory-mcp/`, not in the repo.

Install the binary only (`npm install -g codebase-memory-mcp`, `pip install --user codebase-memory-mcp`, or a checksum-verified release archive). Do not run its own `install` subcommand: it rewrites hooks in `~/.claude/settings.json`, adds agents and a skill, and edits your shell rc. Recommended for large or multi-service codebases only — its authors' benchmark scores it below plain file exploration on answer quality; it wins on tokens.

## Updating every project at once (`--update --recursive`)

```bash
bash ~/.claude/templates/project/init.sh --update --recursive ~/projects   # --dry-run to only look, --yes to skip the question
```

Finds every project dotclaude deployed under the folder (by the settings stub, `settings.local.json.example`, or obsolete hook entries; dependency folders, nested projects and template copies are skipped), derives each one's flags from its `.mcp.json` (`--ui`, `--codebase-memory`, and `--xcode` on macOS), shows the plan and asks once. It then runs `init --update` in each, pruning obsolete hooks and removing obsolete MCP servers with their permissions; obsolete directories such as `.serena/` are only listed, because they may hold committed files. `init.ps1` takes the same flags.

## Retired artifacts are pruned on every deploy

dotclaude sometimes stops shipping a piece a project was deployed with — Serena and Graphify (once deployed by `--serena`) were the first. `templates/project/obsolete.json` lists them, and every `init.sh` / `init.ps1` run removes their dead hook entries from `.claude/settings.json` and `settings.local.json` (the scripts behind them are gone from `~/.claude/hooks/`). Obsolete `.mcp.json` servers and directories (`.serena/`, `graphify-out/`) are only reported: `/init-project --update` asks before removing them.

## Database inspection: `db-inspector` agent

The agent is **central** (`~/.claude/agents/db-inspector.md`, available in every project; inert where there is no SQL database). What `/init-project` decides per project is only the client permission: when it detects a SQL stack it adds `Bash(psql:*)` and/or `Bash(sqlite3:*)` (or `Bash(docker compose exec*:*)` when the DB runs in Docker) to the project stub's `permissions.allow`.

### When to use it

The agent is a **read-only database inspector** with two modes:

- **VALIDATE** — verify the database state after a change. Typical prompts:
  - "I just ran the migration that adds `status` to `orders`. Verify all existing rows now have `status='pending'`."
  - "After the new sign-up flow, confirm that a row in `users` AND a row in `profiles` exist for the test email."
  - "Check that the new index on `users.email` actually exists in the database."
- **ANSWER** — read a fact from the database to inform a decision mid-task. Typical prompts:
  - "How many active users are there right now?"
  - "Does a row in `orders` already exist for this `external_id`?"
  - "What columns does the `invoices` table have, and which are nullable?"

It still defers trivial one-line SELECTs to the main session (a raw `psql` call is faster than spinning up an agent); delegate here when the question needs schema introspection or several chained queries.

The agent runs read-only queries (SELECT / EXPLAIN / `\d` / `.schema`), refuses any mutating statement, and returns either a synthesized verdict (`VERDICT: OK | FAIL | INCONCLUSIVE`) or the requested data plus the query that produced it (`ANSWER`) — it does NOT dump full result sets into your main context.

### Configuration

The agent reads `DATABASE_URL` from the environment (or `.env` / `.env.local`). It auto-detects the engine from the URL scheme:

| URL prefix | Engine | Required client |
|---|---|---|
| `postgres://` / `postgresql://` | Postgres | `psql` |
| `sqlite://` or any path ending in `.db` / `.sqlite` / `.sqlite3` | SQLite | `sqlite3` |

Install the client if missing:
- Postgres: `apt install postgresql-client` (Linux) / `brew install libpq` (macOS).
- SQLite: `apt install sqlite3` (Linux) / present by default (macOS).

**Database in Docker?** If there is no host client but the DB runs in a container, the agent shells in with `docker compose exec -T <db-service> psql ...` (the `-T` disables TTY allocation, required for non-interactive use). It discovers the service from `docker compose ps` / the compose file. This needs `Bash(docker compose exec*:*)` in `permissions.allow` — `/init-project` adds it when it detects a Dockerised DB.

### Relation to Postgres MCP Pro (if also enabled)

The agent and the MCP **coexist** — they cover different jobs:

| Task | Use |
|---|---|
| Validate post-change state ("did my migration land?") | `db-inspector` agent |
| Read a fact mid-task ("how many active users?", "does this row exist?") | `db-inspector` agent (ANSWER mode) — or Postgres MCP Pro if active |
| Quick one-line ad-hoc query during development | Postgres MCP Pro, or a raw `psql` call (cheaper than the agent for trivial reads) |
| Performance analysis: `EXPLAIN`, hypothetical indexes, health checks | Postgres MCP Pro |
| SQLite or any non-Postgres SQL DB | `db-inspector` agent (the MCP is Postgres-only) |
| Working without `uv` / extra installs | `db-inspector` agent (only needs the CLI client, usually already installed) |

The agent is the **safe default**: read-only by hard rules in the prompt, no extra installation, works for both Postgres and SQLite. The MCP adds Postgres-specific superpowers (plan analysis, index tuning) when you opt in.

### Safety model

The agent's read-only enforcement lives in its system prompt: an allowlist of statement prefixes (`SELECT`, `EXPLAIN`, `WITH ... SELECT`, meta-commands) and a denylist of substrings (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `TRUNCATE`, `ALTER`, `CREATE`, `GRANT`, `REVOKE`, `COPY`, `MERGE`, `REPLACE`, `VACUUM`, `REINDEX`, plus statement stacking via `;`). Queries that fail validation are rejected before reaching `psql`/`sqlite3`.

The agent never echoes `DATABASE_URL` (which contains credentials) and redacts passwords if the URL appears in an error message.

This is "trust but verify" defense, not a hard sandbox — if the underlying DB user has write permission, a sufficiently determined adversary inside Claude's context could in theory craft a query that slips past the substring filter. For genuinely sensitive data, use a read-only DB role for the agent's `DATABASE_URL`.

## Standalone deploy (without Claude Code)

The `init.sh` / `init.ps1` scripts work on their own — useful for CI, scripted machine setup, or any scenario where you don't want to invoke `/init-project` first. They deploy only the per-project files; the central core must already be installed (`./install.sh` from the dotclaude repo). The `{{...}}` placeholders in `CLAUDE.md` stay as-is — fill them in manually after. (There is no `{{SCRIPT_EXT}}` to fill anymore: hooks are central, and install.sh/ps1 already resolved the OS form in `~/.claude/settings.json`.)

```bash
# Linux / macOS / WSL
cd <your project>
bash ~/.claude/templates/project/init.sh [--lsp=<plugin>] [--codebase-memory] [--xcode] [--ui]
# Edit CLAUDE.md: replace {{...}} placeholders with real values
```

```powershell
# Windows
cd <your project>
powershell -NoProfile -ExecutionPolicy Bypass -File "$HOME\.claude\templates\project\init.ps1" [--ui]
# Edit CLAUDE.md: replace {{...}} placeholders with real values
```

## Maintaining the template

### Sync rule for hooks

Every hook is a single Python file that serves both platforms; run its case matrix with `--pwsh` to exercise the exact PowerShell command form Windows uses. The deployer (`init.sh` / `init.ps1`) still ships as a pair that must stay logically equivalent: **when you change one, change the other**.

### Promoting a project-local extension to every project

When something you added to a project's `.claude/` proves useful for all projects:

1. Run `/compound` during the session where you discovered the pattern.
2. Or manually, in the **dotclaude repo** (never in `~/.claude/`, which `guard-central-config` blocks and `install.sh` overwrites): reusable artifacts — skills, hooks, rules, agents, output styles — go to `global/.claude/`; per-project surface — the CLAUDE.md template, `docs/`, scaffolds — goes to `templates/project/`.
3. Commit, push, and run `git pull && ./install.sh` on each machine. Central artifacts reach every project immediately; per-project files land on the next `/init-project`.

### Skills: auto-invocable vs manual

- **Auto** (default, `disable-model-invocation: false`): Claude invokes when the description matches the context. Every central skill is auto-invocable; the ones with side effects gate them in their own body instead — `/commit` never commits, merges or pushes without explicit confirmation, `/compound` and `/update-docs` propose their edits first, `/plan-feature` interviews before writing, and `/implement-ui` confirms its component tree via AskUserQuestion before anything is written.
- **Manual** (`disable-model-invocation: true`): only by typing `/<name>`. Only `/init-project`, whose deploy step the user runs in their own terminal.
- `/audit` stays auto-invocable but asks — the mode (defects or improvements) when the request does not say, then in two rounds, categories then depth+scope — before doing any work, so it can never quietly spend a large budget. It also absorbed the old `/security-review`: a pre-commit security pass is `/audit` → Security → Light → Uncommitted changes.

### Model selection policy

Default: `inherit` (use the session's model). Override only when there is a clear reason.

Components in this template that override:

| Component | Model | Why |
|---|---|---|
| `skills/verify` | `haiku` + `context: fork` | Mechanical: runs commands and reports pass/fail. The fork is what keeps `haiku` from applying to the rest of the caller's turn. |
| `skills/changes` | `haiku` + `context: fork` | Mechanical: summarize a diff into bullets; the fork also keeps the full diff out of the main context. |
| `skills/resume-context` | `haiku` + `context: fork` | Mechanical: read three files and structure them. Without the fork, `haiku` ran the rest of the session's first turn. |

Everything else uses `inherit`. Specifically, do NOT downgrade these to `haiku`:
- `researcher` — synthesizing architecture and cross-module flow is reasoning, not lookup. Quick "where is X" lookups go to the built-in Explore agent instead (smaller context; it runs on the session model since Claude Code v2.1.198).
- `code-reviewer`, `debugger` — need reasoning for subtle bugs.
- `db-inspector` — interpreting query results against an expectation requires judgment, not pattern matching.
- `commit`, `compound`, `plan-feature`, `init-project` — need judgment.
- `update-docs` — judging whether a diff is a contract change and how to phrase a new entry is reasoning, not pattern matching.
- `audit` — separating a real dead-code hit from a reflection/entry-point false positive, and spotting the component boundary inside repeated markup, is judgment.
- `readme` — writing prose that reads human (and knowing what must not leak into a public repo) is exactly the kind of work a smaller model gets wrong.

The rule: mechanical work goes to Haiku, work that needs judgment stays on the session's model. Forcing Opus anywhere is wasteful — if the session is on Opus, `inherit` already uses it.

`effort` is a second, orthogonal knob in agent frontmatter (`effort: low|medium|high|xhigh|max`; default: inherit the session's level). The central `researcher`, `debugger`, and `code-reviewer` agents pin `effort: high` so a session running at a lower effort level does not silently degrade work whose whole point is depth. `db-inspector` inherits both model and effort.

## Verify the template is healthy

```bash
ls -R ~/.claude/templates/project/
python3 -m json.tool ~/.claude/templates/project/.claude/settings.json   # must parse without error
```

## See also

- `/compound` — capture learnings and codify them.
- `/resume-context` — rebuild context at session start.
- `~/.claude/CLAUDE.md` — your global preferences.
