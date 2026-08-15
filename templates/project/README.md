# Claude Code project template

The PER-PROJECT half of the dotclaude setup, deployed with `/init-project`. The
reusable core (hooks, agents, skills, rules, output-styles) is NOT here — it is
central in `~/.claude/` (installed from the dotclaude repo's `.claude/`)
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
│   ├── ui.md                    # Visual contract: brand design tokens (palette, type, spacing) + sections
│   ├── user-stories.md          # Behavioral contract: what the user can do (platform-agnostic)
│   └── conventions.md           # How to write the code — portable mirror of the central rules for non-Claude-Code tools
├── .mcp.json              # Only when MCP flags were passed — COMPOSED per server (--serena → serena+graphify, --xcode, --ui → playwright); hand-added servers survive
└── .claude/
    ├── settings.json            # Per-project STUB — only adds project-specific perms (MCP, etc.); base config is central
    └── settings.local.json.example   # Personal overrides; rename to settings.local.json
```

## The central core (in `~/.claude/`, shared by every project)

Installed from the dotclaude repo (`.claude/`) via `install.sh`; updated
for all projects at once with `git pull && ./install.sh`:

- **hooks/** — verify-on-edit, guard-destructive, guard-push-main, detect-secrets, sync-mirror-docs, guard-central-config (blocks editing the central `~/.claude/` config from inside a project), reinject-rules (re-primes the non-negotiable conventions after a context compaction).
- **agents/** — researcher, code-reviewer, debugger, db-inspector.
- **skills/** — verify, commit, changes, plan-feature, compound, resume-context, update-docs, audit, readme, implement-ui (design reference → tokens in `docs/ui.md` → section-by-section build with a screenshot-vs-reference loop; pairs with the playwright MCP deployed by `init.sh --ui`).
- **rules/** — code-quality, security, workflow, ai-collaboration.
- **output-styles/** — dotclaude (opt-in tone/language, enable via `outputStyle`).
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
bash ~/.claude/templates/project/init.sh [--serena] [--xcode] [--ui] [scaffold flags]
```

The MCP flags are added by the skill per the interview: `--serena` (Serena + Graphify), `--xcode` (Apple's `xcrun mcpbridge`, macOS + Xcode 26.3+ only), `--ui` (Playwright browser MCP — lets the model screenshot the running app, which `/implement-ui` uses to verify UI work against a design reference; needs `npx`). Scaffold flags (`--fullstack`, `--runtime=`, `--compose`, `--proxy=`, `--deploy-script`) per the interview. When the script prints `init.sh: deploy OK`, return to Claude Code.

**3. Personalize with Claude Code.** The skill resumes: it fills in placeholders in the deployed `CLAUDE.md` and `settings.json`, sanity-checks `.gitignore`, and verifies the deploy.

### Why the split

Skills that try to copy files into `.claude/` via shell blocks hit two reliability issues. The permission matcher rejects most shell constructs (compound commands, variable expansion against non-`bash` binaries, exit-non-zero) as documented in anthropics/claude-code issues #16561, #43713, #14956. Worse, Claude Code's rule-loading mechanism touches `.claude/rules/*.md` while the skill runs, racing with the file copy (#35096). Every public scaffolding skill avoids in-skill deployment for the same reason — the skill describes intent, the user executes. We follow that pattern.

### Re-deploying: drift report and bullet reconciliation

The reusable core (hooks, agents, skills, rules, output-styles) is central, so to pick up master-repo improvements **in every project at once**, run `git pull && ./install.sh` in the dotclaude clone — nothing per project.

Re-running `/init-project --update` inside a project only touches the per-project surface: it seeds missing files (CLAUDE.md, docs/, the settings stub) and drift-reports `settings.local.json.example` if you edited it. `CLAUDE.md`, `CHANGELOG.md`, and `docs/*` are never overwritten. After the deploy, `/init-project` runs **CLAUDE.md bullet reconciliation**: it compares your `CLAUDE.md` against `CLAUDE.md.template` per section and offers any new bullets via `AskUserQuestion` multiSelect — you pick which to add, nothing is overwritten without consent. See DESIGN.md §19, §23.

## How to extend

The reusable core is central, so **where** you add something depends on whether it should apply everywhere or only to this project:

**Reusable across all your projects → add it to the dotclaude repo (`.claude/`), then `git pull && ./install.sh`:**

| You want to add... | How |
|---|---|
| A repeatable workflow (deploy, test gen, etc.) | New skill in the repo's `.claude/skills/<name>/SKILL.md` |
| A non-negotiable guarantee (must always pass) | New hook in the repo's `.claude/hooks/<name>.{sh,ps1}` + entry in `.claude/settings.json` (lockstep) |
| A specialist agent useful everywhere | New agent in the repo's `.claude/agents/<name>.md` |
| A convention all projects should follow | New file in the repo's `.claude/rules/<topic>.md` (mirror it in `docs/conventions.md`) |

> Editing the installed `~/.claude/` copy from inside a project is blocked by the `guard-central-config` hook — change the source in the repo and re-install.

**Specific to THIS project only → add it in the project's own `.claude/` (it ADDS to the central config, never replaces it):**

| You want to add... | How |
|---|---|
| A project-only convention | Edit `CLAUDE.md` (Don't / Conventions), or create `.claude/rules/<topic>.md` for extensive ones |
| A project-only skill/agent | Create `.claude/skills/<name>/SKILL.md` or `.claude/agents/<name>.md` (lives only here) |
| Permissions for a new MCP, or a project-only override | Add to `permissions.allow` in the project's `.claude/settings.json` stub |
| A new high-level area doc (e.g. `mobile.md`, `bot.md`) | Add the file under `docs/`; `/update-docs` keeps it in sync with the diff |

## Optional MCP: Serena (semantic code intelligence)

[Serena](https://github.com/oraios/serena) is an LSP-backed MCP that exposes symbol-level tools (`find_symbol`, `find_referencing_symbols`, `replace_symbol_body`, `get_symbols_overview`, etc.). When selected during `/init-project`, the deploy merges the `serena` and `graphify` fragments from `templates/project/mcp/` into the project's `.mcp.json`.

**Deterministic tool preference (not just advisory).** Selecting Serena also merges Serena's own drift-prevention hooks into this project's `.claude/settings.json`: `serena-hooks activate` (SessionStart) primes the model to read Serena's instructions, and `serena-hooks remind` (PreToolUse) nudges it back to Serena's symbol tools whenever it over-relies on Grep/Read — silent when you're already using Serena. This is what makes the preference hold over a long session, where advisory CLAUDE.md prose alone tends to decay. The hooks are merged idempotently and never overwrite your own project hooks/permissions.

### Prerequisite (one-time per machine)

Serena is invoked via the `serena` binary. Install it once with `uv`:

```bash
uv tool install -p 3.13 serena-agent@latest --prerelease=allow
```

If `uv` is not installed:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh    # Linux/macOS/WSL
# or: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"   # Windows
```

The template intentionally does NOT use `uvx --from git+https://github.com/oraios/serena ...`. That form works without a global install but adds ~5–15s startup latency per session and re-resolves the package on every cold start. The `uv tool install` approach pins the version, starts instantly, and is the form recommended by Serena's official docs.

### What Serena writes to disk

- `.serena/project.yml` — committed (project-wide config).
- `.serena/memories/*.md` — committed (onboarding summaries written on first run; act as team-shared context).
- `.serena/project.local.yml` — gitignored (personal overrides; the template `.gitignore` already excludes it).
- `.serena/cache/` — gitignored (LSP cache).

### First-run behavior

On the first MCP call after activation, Serena runs an "onboarding" pass: reads key files, derives project structure, writes summaries to `.serena/memories/`. This takes ~30s–2min depending on repo size.

For repos with >1k source files, run once for faster symbol lookups:
```bash
serena project index
```

### Web dashboard (no browser auto-open)

The `.mcp.json` passes `--open-web-dashboard False`, so starting the Serena MCP server does **not** pop open a browser tab on every session — which is noise inside a terminal/IDE agent. The dashboard *server* is left at its default (enabled), so if you ever want Serena's live log/tool view you can open it manually at `http://127.0.0.1:24282/dashboard/` while the server is running (24282 is the base port; Serena picks the next free port up from there if it's taken). To stop the dashboard from running at all, add `--enable-web-dashboard False` to the serena args in `.mcp.json` (the deploy intentionally does not, per Serena's own recommendation to keep the dashboard available but not auto-opened).

### When to use Serena tools vs native Claude Code tools

See the "Serena" block in the deployed `CLAUDE.md` (only present if Serena was selected during `/init-project`). Short version: symbol-level operations (find a definition, rewrite a function body, list references) go through Serena; plain text reads/edits stay on `Read` and `Edit`.

### Permissions

`/init-project` adds `mcp__serena__*` (and `mcp__graphify__*`, see below) to `permissions.allow` automatically when Serena is selected. The MCP itself runs without `execute_shell_command` (disabled under `--context claude-code`), so it cannot run shell commands — Claude Code's `Bash` tool handles that.

## Companion MCP: Graphify (codebase knowledge graph)

[Graphify](https://github.com/safishamsi/graphify) ships in the **same `.mcp.json`** as Serena (deployed together by `--serena`) because they are complementary: Serena works at the **symbol** level, Graphify at the **graph** level — a queryable knowledge graph of how the whole codebase (code + docs + schema) relates. Use Graphify to understand structure and ripple effects ("what depends on this", "what breaks if I change X"), then Serena to act precisely on the symbols involved.

Graphify is a **Skill (builds the graph) + an MCP server (serves it)**, set up in this order:

1. **Build the graph:** install once with `uv`, then build:
   ```
   uv tool install graphifyy
   /graphify .             # builds graphify-out/graph.json (run inside the project)
   ```
   You do **not** need to run `graphify install`. The graph-first *determinism* — a `PreToolUse` nudge toward `graphify query` when you grep/find or read source files one-by-one while a graph exists — ships centrally as `prefer-graphify.{sh,ps1}` and is merged into this project's hooks by `--serena` (gated on the graph existing, so it's silent until you build it). `--serena` also runs `graphify hook install` for you (git post-commit/post-checkout auto-rebuild, AST-only, no API cost) so the graph never goes stale and the nudges point at current data. We deliberately avoid `graphify install`/`graphify claude install`: they append a raw block to `CLAUDE.md`, drop a per-project skill, and rewrite `settings.json` destructively.
2. **MCP server (secondary):** the `graphify` entry in `.mcp.json` exposes the built graph for repeated tool-call access (`query_graph`, `get_neighbors`, `shortest_path`, `get_pr_impact`, …). **It reads `graphify-out/graph.json` and will not start until that file exists** — so on a fresh project the `graphify` MCP server shows as unavailable until you run `/graphify .` at least once. Serena (same `.mcp.json`) starts independently and is unaffected.

`graphify-out/` is build output and is gitignored — with the auto-rebuild hook it changes on every commit, so versioning it would put a multi-MB diff in each commit. Each dev builds their own with `/graphify .`.

### What Graphify writes to disk

- `graphify-out/graph.json` — the built graph (gitignored; auto-rebuilt per commit).
- `graphify-out/` — cache and intermediate artifacts (gitignored).

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
bash ~/.claude/templates/project/init.sh [--serena] [--xcode] [--ui]
# Edit CLAUDE.md: replace {{...}} placeholders with real values
```

```powershell
# Windows
cd <your project>
powershell -NoProfile -ExecutionPolicy Bypass -File "$HOME\.claude\templates\project\init.ps1" [--serena] [--ui]
# Edit CLAUDE.md: replace {{...}} placeholders with real values
```

## Maintaining the template

### Sync rule for hooks

The hooks ship in two variants — `.sh` (Bash) and `.ps1` (PowerShell) — that must stay logically equivalent. **When you change one, change the other**. Diverging silently breaks Windows users.

### Promoting a project-local extension to every project

When something you added to a project's `.claude/` proves useful for all projects:

1. Run `/compound` during the session where you discovered the pattern.
2. Or manually, in the **dotclaude repo** (never in `~/.claude/`, which `guard-central-config` blocks and `install.sh` overwrites): reusable artifacts — skills, hooks, rules, agents, output styles — go to `global/.claude/`; per-project surface — the CLAUDE.md template, `docs/`, scaffolds — goes to `templates/project/`.
3. Commit, push, and run `git pull && ./install.sh` on each machine. Central artifacts reach every project immediately; per-project files land on the next `/init-project`.

### Skills: auto-invocable vs manual

- **Auto** (default, `disable-model-invocation: false`): Claude invokes when the description matches the context. Use for `/verify`, `/changes`, `/resume-context`, `/update-docs`, `/readme`, `/implement-ui` (its side effects — components, `docs/ui.md` — are the requested work itself, and the component tree is confirmed via AskUserQuestion before anything is written).
- **Manual** (`disable-model-invocation: true`): only by typing `/<name>`. Use for actions with visible side effects: `/commit`, `/plan-feature`, `/compound`, `/init-project`.
- `/audit` stays auto-invocable but asks — in two rounds, categories then depth+scope — before doing any work, so it can never quietly spend a large budget. It also absorbed the old `/security-review`: a pre-commit security pass is `/audit` → Security → Light → Uncommitted changes.

### Model selection policy

Default: `inherit` (use the session's model). Override only when there is a clear reason.

Components in this template that override:

| Component | Model | Why |
|---|---|---|
| `skills/verify` | `haiku` + `context: fork` | Mechanical: runs commands and reports pass/fail. The fork is what keeps `haiku` from applying to the rest of the caller's turn. |
| `skills/changes` | `haiku` + `context: fork` | Mechanical: summarize a diff into bullets; the fork also keeps the full diff out of the main context. |
| `skills/resume-context` | `haiku` | Mechanical: read three files and structure them. |

Everything else uses `inherit`. Specifically, do NOT downgrade these to `haiku`:
- `researcher` — synthesizing architecture and cross-module flow is reasoning, not lookup. Quick "where is X" lookups go to the built-in Explore agent (Haiku) instead.
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
