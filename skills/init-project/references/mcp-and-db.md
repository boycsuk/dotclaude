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
- `codebase-memory` — persistent code graph (deployed by `--codebase-memory`;
  see the section below before recommending it)
- `xcode` — Apple's own Xcode bridge (iOS/macOS projects only; **offer it only on
  a macOS host with an Xcode project**, and see the section below before doing so)

Remember the selection. You will write the permissions and CLAUDE.md section in step 6.

### codebase-memory-mcp prerequisite (`--codebase-memory`)

[codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) (DeusData,
MIT, a single C binary) keeps a persistent graph of the code: callers and call
paths (`trace_path`), the impact of the current diff (`detect_changes`),
architecture overviews (`get_architecture`), dead code, links between
services. It answers *structural* questions; the LSP plugin (§3b) answers
questions about *one symbol*; Grep/Read stay for literal text and config.

**Recommend it only for large or multi-service codebases.** Its authors'
own benchmark (arXiv:2603.27277) scores 83% answer quality against 92% for
plain file exploration: it saves tokens, it does not answer better. On a small
repo it is context cost for no gain.

Type resolution varies by language: Python, TypeScript/JavaScript, Go, Rust,
Java, Kotlin, C#, C/C++ and PHP get its "hybrid LSP" layer (a C
re-implementation, not a real language server); everything else, including
Bash, PowerShell and Swift, is tree-sitter only — weaker for call resolution.
Mention that when the project's language is in the second group.

**Install the binary only** (the deploy exits 8 and prints these if missing):
`npm install -g codebase-memory-mcp`, `pip install --user codebase-memory-mcp`,
or the release archive from GitHub verified against its `checksums.txt`.
**Never** run `codebase-memory-mcp install` or the upstream `curl | bash`
one-liner: that subcommand writes hook entries into `~/.claude/settings.json`
(which dotclaude's `install.sh` owns and would overwrite), adds three agents
and a skill to `~/.claude/`, appends a PATH line to the shell rc, and
configures every other AI client it detects. dotclaude wires the server
itself; DESIGN.md §33 has the reasoning.

What the flag does: merges the `codebase-memory-mcp` server into `.mcp.json`
and its 13 read-only tools into `permissions.allow` by exact name.
`index_repository`, `delete_project`, `manage_adr` and `ingest_traces` stay on
ask. The index lives in `~/.cache/codebase-memory-mcp/` (outside the repo, so
nothing to gitignore; `.codebase-memory/` only appears with its opt-in
`persistence: true`, and the template's `.gitignore` already covers it). On
WSL, keep that cache on the Linux filesystem, not under `/mnt/<drive>`
(override with `CBM_CACHE_DIR`).

The model is told when to use the graph by the central `code-intel-context`
hook (session start and every code-reading subagent) and the
`explore-graph-prompt` hook (every Explore delegation) — not by CLAUDE.md
prose. Both stay silent in projects without the server.

### Xcode MCP prerequisite (`--xcode`)

Apple's own MCP server, shipped with **Xcode 26.3+** as `xcrun mcpbridge`. Only
offer it when the host is macOS **and** the project builds for an Apple platform
(`*.xcodeproj` / `*.xcworkspace` / `Package.swift`). Nothing to install: it comes
with Xcode. The user must enable it once in **Xcode > Settings > Intelligence**.

`--xcode` MERGES the `xcode` server into `./.mcp.json` rather than aborting when
the file exists, so it combines with the other MCP flags in either order and
re-running is idempotent. Exit 5 on a non-macOS host, exit 6 if `xcrun mcpbridge`
is missing (wrong Xcode selected — check `xcode-select -p`).

Add `mcp__xcode__*` to `permissions.allow` in the project stub (step 6).

**The one operational constraint, worth stating to the user verbatim:** the
server is an XPC bridge into a *running* Xcode process. Xcode must be open with
the project **before Claude Code starts**, or the server shows as unavailable —
and opening a different project mid-session does not reconnect it.

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

## 3b. Code intelligence: the LSP plugin (`--lsp=<plugin>`)

Not an MCP, but decided here because it is the other half of "what tools does
the model get in this project". Claude Code's official LSP plugins give the
model a read-only `LSP` tool (go-to-definition, references, hover types,
symbols, call hierarchy) and push the language server's diagnostics after
every edit ("Found N new diagnostic issues"). That replaces what Serena was
used for, natively (DESIGN.md §32).

1. Map the language(s) from §2 through the catalog:
   `~/.claude/templates/project/lsp-plugins.json` (plugin → languages, binary,
   install hint). Only the 13 official `claude-plugins-official` plugins are
   listed; if the project's language has none (Bash, PowerShell, …), tell the
   user plainly and add nothing — do not search for community plugins.
2. Tell the user which language-server binary the plugin needs and the
   catalog's install hint. The deploy script probes PATH itself and repeats
   the hint as a WARN if the binary is missing; the plugin stays inert
   ("Executable not found in $PATH" in `/plugin` → Errors) until it exists.
3. Add `--lsp=<plugin>` to the step 5 command, once per main language. No
   question needed for the main language — it is on by default for code
   projects; ask only to choose among secondary languages in a polyglot repo.

The flag runs `claude plugin install <plugin>@claude-plugins-official --scope
project`, which installs the plugin and records it under `enabledPlugins` in
`.claude/settings.json`. Listing it there by hand is NOT enough: an uninstalled
plugin stays off even when enabled (verified 2026-10-03), so teammates who
clone the project run the same `claude plugin install … --scope project` once
(or accept the install prompt Claude Code shows).

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
