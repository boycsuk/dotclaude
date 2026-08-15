# Reference: MCPs and database stack (§3, §4)

Loaded by `SKILL.md` after the stack interview on a first-time deploy (or the
Reconfigure path). Covers which MCP servers to authorize and detecting a SQL
stack so step 6 can add the right client permission to the project settings stub.

## 3. Ask which MCPs to authorize

List globally available MCP servers using the regular `Bash` tool:

`ls "$HOME/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/"`

If the directory does not exist, continue with the candidate list anyway.

Ask via AskUserQuestion (multiSelect) which MCPs the user wants for this project. Common candidates:
- `playwright` — browser automation (deployed by the `--ui` flag; recommend it
  for any project with a web UI — see the section below)
- `github` / `gitlab` — code hosting
- `linear` / `asana` — task tracking
- `terraform` — infrastructure
- `serena` — semantic code intelligence (symbol-level retrieval/editing)
- `graphify` — codebase knowledge graph (queryable code+docs+schema graph), Serena's companion
- `xcode` — Apple's own Xcode bridge (iOS/macOS projects only; **offer it only on
  a macOS host with an Xcode project**, and see the section below before doing so)

Remember the selection. You will write the permissions and CLAUDE.md section in step 6.

### Serena + Graphify prerequisite

Serena and Graphify are complementary and ship together in the same
`.mcp.json` (deployed by the `--serena` flag): Serena gives **symbol-level**
navigation and editing (find_symbol, replace_symbol_body), Graphify gives a
**graph-level** view of how the whole codebase relates (query_graph,
get_neighbors, shortest_path, impact analysis). Use Serena to act precisely on
a known symbol; use Graphify to understand structure and ripple effects before
acting.

**`--serena` also deploys Serena's drift-prevention hooks.** Beyond copying
`.mcp.json`, `init.sh --serena` MERGES the hook block from
`templates/project/.claude/serena-hooks.json` into the project's
`.claude/settings.json`. These are Serena's own official hooks (oraios/serena
#1201) — `serena-hooks activate` (SessionStart) and `serena-hooks remind`
(PreToolUse) — and they are what makes the model *deterministically* prefer
Serena's tools over Grep/Edit instead of drifting back over a long session. The
CLAUDE.md/rules prose is the soft layer (it decays under context compaction);
the hooks are the hard layer (they re-prompt at the harness level). The merge is
idempotent and non-destructive — it de-duplicates by command and preserves any
project-specific hooks/permissions already in the stub.

**Graphify's graph-first determinism ships as OUR OWN central hook, not via
`graphify install` (revised 2026-07-09).** `prefer-graphify.{sh,ps1}` lives in
`global/.claude/hooks/` (same pattern as `prefer-serena-bash`): a `PreToolUse`
nudge on `Bash` (catches `grep`/`rg`/`find`/`fd`) and on `Read|Glob|Grep`
(catches reading source files one-by-one), pointing at `graphify query` when
`graphify-out/graph.json` exists — it *nudges, never blocks*, and is gated on the
graph so it's silent in Serena-only projects. It is wired through
`serena-hooks.json` (merged by `--serena`), exactly like `prefer-serena-bash`. We
deliberately do NOT run `graphify install`/`graphify claude install`: they append
a raw `## graphify` block to CLAUDE.md, drop a per-project skill, and rewrite
`settings.json` destructively (in one project that clobbered Serena's own hooks).
What `--serena` DOES run for Graphify is `graphify hook install` — the git
post-commit/post-checkout auto-rebuild — so the graph never goes stale.

Both require the host to have their binaries, both installed via `uv` (so the
same `uv` prerequisite covers both):

```
# Serena
uv tool install -p 3.13 serena-agent@latest --prerelease=allow
# Graphify
uv tool install graphifyy
# (do NOT run `graphify install` — see below. `--serena` runs `graphify hook install`
#  for you; the graph-first nudge ships centrally as prefer-graphify.)
```

(Requires `uv`: `curl -LsSf https://astral.sh/uv/install.sh | sh`.)

If `serena` is missing, the deploy command in step 5 will exit with code 4 and print the install instructions — surface that to the user verbatim.

**Graphify's opt-in is now just ONE user step; `--serena` handles the rest:**
1. **`/graphify .`** (the skill, once per project): builds the knowledge graph
   into `graphify-out/graph.json`. This is the step that *creates* the graph and
   the one the `graphify` MCP server depends on. **This is the only step the user
   runs.**
2. The **graph-first nudge** is already wired: `prefer-graphify.{sh,ps1}` (central)
   is merged into the project's hooks by `--serena` via `serena-hooks.json`. It is
   gated on `graphify-out/graph.json`, so it's inert until step 1 runs — safe to
   have present on day 1.
3. The **auto-rebuild** is already wired: `init.sh --serena` runs
   `graphify hook install` (git post-commit/post-checkout, AST-only, no API cost)
   so the graph never goes stale and the nudge points at current data.

Do NOT run `graphify install`/`graphify claude install`: they append a raw
`## graphify` block to CLAUDE.md, drop a per-project skill, and rewrite
`settings.json` destructively.

Then the **MCP server** (the `graphify` entry in `.mcp.json`) exposes the
*already-built* graph for repeated tool-call access. **It reads
`graphify-out/graph.json` and will fail to start until that file exists** — i.e.
until `/graphify .` has been run at least once. This is expected: a fresh project
shows the `graphify` MCP server as unavailable until the first graph build.
Serena (in the same `.mcp.json`) starts independently and is unaffected.

### Xcode MCP prerequisite (`--xcode`)

Apple's own MCP server, shipped with **Xcode 26.3+** as `xcrun mcpbridge`. Only
offer it when the host is macOS **and** the project builds for an Apple platform
(`*.xcodeproj` / `*.xcworkspace` / `Package.swift`). Nothing to install: it comes
with Xcode. The user must enable it once in **Xcode > Settings > Intelligence**.

`--xcode` MERGES the `xcode` server into `./.mcp.json` rather than aborting when
the file exists, so `--serena --xcode` together is supported in either order and
re-running is idempotent. Exit 5 on a non-macOS host, exit 6 if `xcrun mcpbridge`
is missing (wrong Xcode selected — check `xcode-select -p`).

Add `mcp__xcode__*` to `permissions.allow` in the project stub (step 6).

**The one operational constraint, worth stating to the user verbatim:** the
server is an XPC bridge into a *running* Xcode process. Xcode must be open with
the project **before Claude Code starts**, or the server shows as unavailable —
and opening a different project mid-session does not reconnect it. This is the
same shape as the `graphify` server being inert until a graph exists.

**The 20 tools.** Files: `XcodeRead`, `XcodeWrite`, `XcodeUpdate`, `XcodeGlob`,
`XcodeGrep`, `XcodeLS`, `XcodeMakeDir`, `XcodeRM`, `XcodeMV`. Build/test:
`BuildProject`, `GetBuildLog`, `RunAllTests`, `RunSomeTests`, `GetTestList`.
Diagnostics: `XcodeListNavigatorIssues`, `XcodeRefreshCodeIssuesInFile`,
`ExecuteSnippet`. Apple-specific: `RenderPreview` (SwiftUI preview → screenshot,
no build needed), `DocumentationSearch` (Apple docs + WWDC transcripts),
`XcodeListWindows`.

**`XcodeListWindows` is the entry point, not a utility.** `BuildProject` and
`RenderPreview` require a `tabIdentifier`, obtainable only from it — so it is
always the first call in a chain. With several Xcode instances open, set
`MCP_XCODE_PID` to disambiguate.

**Known issue to surface if the user hits it.** Tools that go through macOS
Automation (`BuildProject`, `RenderPreview`, `ExecuteSnippet`, `RunSomeTests`,
`GetTestList`) hung indefinitely for CLI clients, because TCC will not persist an
Automation grant for a binary without a stable reverse-DNS bundle identifier
(anthropics/claude-code #23550, #27557). **Both issues were closed by an
inactivity bot, not by a fix, and no newer report exists as of 2026-08** — so
treat this as unverified-either-way rather than resolved. Read-only tools
(`XcodeRead`, `XcodeGrep`, `XcodeLS`) were never affected. If the permission
dialog reappears on every call, the workaround is
[dazuiba/xcode-cli-skill](https://github.com/dazuiba/xcode-cli-skill), a
persistent local bridge that reduces it to once per boot.

**What this server deliberately does NOT cover**, in case the user asks for it
later: UI automation (tapping/typing through the app), LLDB breakpoints, physical
devices, macOS-app and SPM builds, and per-file coverage. Those live in
[XcodeBuildMCP](https://github.com/getsentry/XcodeBuildMCP) (82 tools, no running
Xcode required). It was evaluated and deliberately left out of the template —
adding a second server costs context in every session. If the user's work turns
out to need app-driving or on-device builds, that is the moment to add it, with
`claude mcp add`, not a template change.

### Playwright prerequisite (`--ui`)

Microsoft's official browser-automation MCP (`@playwright/mcp`), launched via
`npx` — the only host prerequisite is npx itself (ships with Node.js); the
package is fetched on demand. `--ui` MERGES the `playwright` server into
`./.mcp.json`, idempotently and combinable with the other MCP flags in any
order. Exit 7 if `npx` is missing. First use may download a browser build —
slow once, then cached.

**Why it matters beyond scraping/E2E:** it gives the model eyes. With it, UI
work follows the visual verification loop — implement, screenshot the running
app, compare against the design reference, fix, repeat — instead of coding
blind. The central `/implement-ui` skill drives exactly that loop (tokens into
`docs/ui.md` first, then section-by-section implementation with a
screenshot-vs-reference gate). **Recommend `--ui` for any project with a web
UI**, not only when the user asks for browser automation.

Add `mcp__playwright__*` to `permissions.allow` in the project stub (step 6).

## 4. Detect database stack (for SQL client permissions)

The `db-inspector` agent is now **central** (in `~/.claude/agents/`, always
available — read-only, inert if the project has no DB), so you no longer deploy
or drop it. Detecting a SQL stack here serves one purpose: decide whether to add
SQL-client permissions (`Bash(psql:*)` / `Bash(sqlite3:*)`, or the Docker/
PowerShell equivalents) to the project's `settings.json` stub in step 6.

**Detection signals:**
- **Postgres:** `pg`, `psycopg`, `psycopg2`, `asyncpg`, `pg-promise` (Node); `sqlx` + `postgres`, `tokio-postgres`, `diesel` + `postgres` (Rust); `lib/pq`, `pgx`, `gorm.io/driver/postgres` (Go); `psycopg2`, `psycopg`, `asyncpg`, sqlalchemy with postgres dialect (Python).
- **SQLite:** `better-sqlite3`, `sqlite3` (Node); `rusqlite`, `sqlx` + `sqlite` (Rust); `mattn/go-sqlite3`, `gorm.io/driver/sqlite` (Go); any `*.db` / `*.sqlite` / `*.sqlite3` in repo root, `data/`, `db/`, or `prisma/`.

Remember whether a SQL stack was found, so step 6 can add the client permission to the project stub. (`--db` may still be passed to `init.sh` for compatibility, but it is a no-op now — it neither adds nor removes the central agent.)

**Host vs Docker variants** (decides which permission to add to the stub):

- **DB on host** (no Docker, or Postgres outside compose). Postgres: user sets `DATABASE_URL` and installs `psql` (`apt install postgresql-client` / `brew install libpq`). SQLite: user installs `sqlite3` (`apt install sqlite3` / preinstalled on macOS). Add `Bash(psql:*)` / `Bash(sqlite3:*)` to the project stub.
- **DB in Docker** (from step 2b). The db-inspector shells into the container. Add `Bash(docker compose exec*:*)` to the project stub instead of (or alongside) `Bash(psql:*)`. In the deployed CLAUDE.md, document the query command as `docker compose exec -T <db-service> psql -U <user> <dbname>` (the `-T` disables TTY allocation, required for non-interactive use by the agent) and warn that `DATABASE_URL` should use the host-side hostname (typically `localhost`) when read from the host, or the service name (typically `postgres`/`db`) when read from another container.

If Docker is involved, also mention to the user that the first query may be slow (the container has to be running). `docker compose up -d <db-service>` brings it up if it's stopped.
