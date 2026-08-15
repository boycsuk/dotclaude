---
name: init-project
description: Sets up the portable .claude/ template in the user's project — stack detection, an MCP/DB interview, and placeholder personalization (the full procedure is in the body). Use when the user invokes /init-project or asks to scaffold the dotclaude setup into a project.
disable-model-invocation: true
allowed-tools: Bash(ls:*) Bash(cat:*) Bash(grep:*) Bash(find:*) Bash(uname:*) Bash(pwd:*) Bash(python3:*) Bash(test:*) Read Edit Write
---

# Init Project

> **Converse with the user in Castilian Spanish (Spain).** Informal "tú"; "vale", "ordenador", "móvil" — avoid Latin American variants. AskUserQuestion questions, messages you show, summaries — all in Castilian. Everything written into files (CLAUDE.md, settings.json, comments, identifiers) stays in English — and so does this skill's own copy: the question/option texts below are written in English and rendered in Castilian when presented to the user.

This skill plans and personalizes a `.claude/` deployment, but **does not execute the file copy itself**. The user runs a single `bash` command in their own terminal afterwards.

> **Why the split.** Claude Code's permission matcher and rule-loading mechanism conflict with skills that deploy files in `.claude/` via `!`-blocks (anthropics/claude-code issues #35096 race-condition-on-rule-load, #14956 allowed-tools-ignored, #16561 compound-command-matcher, #43713 simple_expansion-rejected). Every public scaffolding skill (anthropics/skills, vercel-labs/skills, etc.) avoids in-skill shell deployment for the same reason. This skill follows the documented pattern: **describe intent, let the user execute.**

> **This file is a router — load detail on demand.** The heavy phases live in
> `references/*.md` and are NOT in context until you read them. Read a
> reference file with the `Read` tool only when the flow reaches that branch:
> - `references/update-mode.md` — re-run path (§1b/§1c/§1d/§1e). Read only if step 1
>   finds an existing `.claude/`. §1e offers Serena/Graphify improvements to
>   projects that opted into Serena before the template added them.
> - `references/stack-interview.md` — stack / Docker / deployment / version
>   pinning (§2/§2b/§2c/§2d). Read on a first-time deploy or the Reconfigure path.
> - `references/mcp-and-db.md` — MCP authorization and SQL-stack detection
>   (§3/§4). Read after the stack interview on a first-time deploy or Reconfigure.
>
> Don't pre-read them. A CLI-tool deploy with no DB never touches the MCP/db
> file; a refresh never touches the stack interview. That is the point.

## 0. Opening question: does the user want to describe the project?

**This is the first step, before any detection or technical question.** Before getting into stack, Docker, deployment, or versions, give the user the chance to tell you what they want to build. If they do, every later question is biased toward technologies and options that fit that goal; if they prefer not to, follow the original neutral flow.

Ask via AskUserQuestion:

- "Do you want to tell me what kind of project you're building before we start the technical questions?"
  - **Yes, let me explain** — the user describes the project in free text (via "Other" or in the next turn) and you use it as context to focus the following questions.
  - **No, follow the standard flow** — no context given; later questions are asked neutrally, same as before.

### If the user picks "Yes"

Ask for a short description: what the product does, who uses it, which pieces it has (API, web, mobile, CLI, batch, etc.), any obvious constraints (self-hosted, on-prem, low-cost, edge, real-time, high-traffic, offline-first…). Don't demand a perfect brief — one or two sentences are enough.

**Keep the description in working memory** and use it as a filter and bias in every later step. The general rule: in each AskUserQuestion of the following phases (stack, Docker, deployment, versions, MCPs, db), reorder the options to put the one that fits the description first and tag it `(Recommended)`, and adjust each option's description to explain why it does or doesn't fit. Mapping examples:

- **Project type / language / framework**: "daily price scraper" → Script/CLI or backend job; "online shop for small businesses" → Fullstack; "native mobile app" → React Native / Swift / Kotlin; "ML model served as an API" → Python + FastAPI.
- **Docker**: "self-hosted / VPS / homelab" → bias toward Docker Compose; "Vercel / serverless / Cloudflare Workers" → advise against Compose.
- **Deployment**: "SaaS for customers" → VPS or container platform; "tool that runs on my machine" → No deployment; mentions HTTPS / own domains → Caddy + Let's Encrypt.
- **Versions**: explicit constraints ("the client's Ubuntu 20.04") narrow the options (Node 20 LTS, not 22).
- **MCPs**: "scraping / E2E tests / web UI" → playwright; "tickets / Linear / Asana" → their MCP; "monorepo / semantic navigation" → serena; "iOS / macOS / Swift app" → xcode (only on a macOS host).
- **DB**: "catalogs / users / transactions" → PostgreSQL; "cache / sessions / queues" → Redis; "documents / flexible JSON" → Mongo; "embedded / single machine / edge" → SQLite.

**The bias is a suggestion, not a decision.** The user can always pick "Other" or a different option. **If they contradict the description** (said "daily scraper" but picks "Frontend"), don't push back: accept the change and keep biasing with the combined information.

### If the user picks "No"

Don't bring the description up again. Continue from §1 with the neutral flow. Later questions are presented in neutral order, without biased recommendations.

### If this is a re-run (step 1 detects an existing `.claude/`)

Skip §0. The project already exists and its high-level description already lives in its CLAUDE.md. Asking again would be redundant.

## 1. Verify context and platform

Use the regular `Bash` tool to gather context. None of these need to be `!`-blocks.

- `pwd` — current project directory.
- `uname -s` — `Linux` or `Darwin` → the user runs the `bash`/`init.sh` command in step 5. If it fails (native Windows without WSL), they run `init.ps1` instead.
- `uname -r` — if output contains `microsoft`, it's WSL → still the `bash` path.
- `ls -la .claude` — **if `.claude/` already exists, this is a re-run.** Load `references/update-mode.md` and follow it instead of the first-time flow below.
- `ls package.json pyproject.toml requirements.txt Cargo.toml go.mod Gemfile Makefile` — present files are stack signals.
- `ls "$HOME/.claude/templates/project"` — must exist. If not, instruct the user to clone the dotclaude repo and run `./install.sh`.

Tell the user which platform was detected and confirm before continuing.

## 2. Stack interview (first-time deploy)

For a first-time deploy, **load `references/stack-interview.md`** and work through it: detect or interview the stack (§2), Docker (§2b), deployment target (§2c), and pin versions (§2d). It writes the `## WHAT — *` sections of the deployed CLAUDE.md and decides which scaffold flags step 5 needs. (On the Reconfigure path, `update-mode.md` tells you to load the same file but pre-fill from the existing CLAUDE.md.)

## 3-4. MCPs and database stack

After the stack interview, **load `references/mcp-and-db.md`**: ask which MCP servers to authorize (§3) and detect whether there is a SQL stack (§4, so step 6 can add the right client permission to the project settings stub). Skip on a pure refresh.

## 5. Tell the user the exact command to run

Based on steps 1-4, choose the right flags. **Show the user this block verbatim** — do NOT try to execute it from the skill. The user copies it into their own terminal.

### Core flags

| Flag | When to include |
|---|---|
| `--serena` | User selected Serena MCP in §3. Deploys the serena + graphify `.mcp.json` bundle AND merges Serena's drift-prevention hooks into the project `settings.json` (makes the model deterministically prefer Serena's tools — see `references/mcp-and-db.md`). |
| `--xcode` | User selected the Xcode MCP in §3. **macOS + Apple-platform projects only** (`*.xcodeproj` / `*.xcworkspace` / `Package.swift`) — never offer it otherwise. Merges Apple's `xcode` server (`xcrun mcpbridge`, Xcode 26.3+) into `.mcp.json`; combines with `--serena` in either order. See `references/mcp-and-db.md`. |
| `--ui` | User selected the Playwright MCP in §3 — recommend it whenever the project has a web UI. Merges the `playwright` browser server (`npx @playwright/mcp`) into `.mcp.json`: the model can navigate, resize and screenshot the running app, which is what the central `/implement-ui` skill uses to verify UI work against a design reference. Combines with the other MCP flags in any order. See `references/mcp-and-db.md`. |
| `--update` | Re-run path (see `references/update-mode.md`). Never on a first-time deploy. |
| `--db` | Optional, no-op (kept for compatibility). The db-inspector agent is central now; a SQL stack only affects which client permission you add to the project `settings.json` stub in step 6, not a flag. |

### Scaffold flags (first-time deploy only — re-runs skip files that exist)

Include based on the interview answers from `references/stack-interview.md`:

| Flag | When to include |
|---|---|
| `--fullstack` | Project type was "Fullstack". Creates `backend/`, `clients/web/`, `scripts/` and writes `.env.example`. |
| `--runtime=node` / `--runtime=python` | Project type is Fullstack/API AND Docker is in use. Writes a `Dockerfile` (non-root user) plus a matching `.dockerignore`. Skip on other runtimes (Rust/Go scaffolds not yet shipped). |
| `--compose` | Docker Compose in use. Writes `docker-compose.yml` with `app` + Postgres `db` services. |
| `--proxy=caddy` | Caddy chosen as reverse proxy. Writes a minimal `Caddyfile`. (`--proxy=nginx` is reserved but not yet implemented.) |
| `--deploy-script` | Project type is Fullstack OR VPS hosting. Writes a `./deploy.sh` skeleton (the `.ps1` variant on Windows) with `start`/`stop`/`restart`/`logs` subcommands; the user fills in the bodies. |

### Examples

**Empty Fullstack project with Node, Postgres in Docker, Caddy on a VPS:**

```
cd <path from step 1>
bash ~/.claude/templates/project/init.sh --fullstack --runtime=node --compose --proxy=caddy --deploy-script
```

(A SQL stack adds `Bash(psql:*)` / `Bash(docker compose exec*:*)` to the project's `settings.json` stub in step 6 — no flag needed; the db-inspector agent is already central.)

**Existing Python API project re-running with Serena:**

```
cd <path from step 1>
bash ~/.claude/templates/project/init.sh --update --serena
```

**CLI tool, no Docker, no deployment:**

```
cd <path from step 1>
bash ~/.claude/templates/project/init.sh
```

### Windows (native, no WSL)

Substitute the bash command with:

```
powershell -NoProfile -ExecutionPolicy Bypass -File "$HOME\.claude\templates\project\init.ps1" [same flags]
```

Tell the user to run the command, then come back to this session and confirm when it printed `init.sh: deploy OK` (or `init.ps1: deploy OK`).

If the script fails:
- Exit 1: template missing — `cd ~/projects/dotclaude && ./install.sh` to refresh.
- Exit 3: retired. `.mcp.json` is composed per-server now, so there is no whole-file conflict to abort on. A project still running an older `init.sh` can emit it — tell that user to re-run `./install.sh` from the dotclaude clone.
- Exit 4: `serena` binary missing. Install it (see `references/mcp-and-db.md`) and re-run.
- Exit 5: `--xcode` on a non-macOS host. Drop the flag — Apple's mcpbridge ships with Xcode.
- Exit 6: `xcrun mcpbridge` unavailable. Needs Xcode 26.3+; check `xcode-select -p` points at it, then enable MCP in Xcode > Settings > Intelligence.
- Exit 7: `npx` missing (`--ui` needs it to launch the playwright server). Install Node.js — it ships npx — and re-run.

### Pointer to `create-X` for app code

The scaffold writes infrastructure (Dockerfile, compose, proxy, deploy skeleton, env example, directory shell) but **does not** generate framework-specific application code — that is what each framework's official scaffolder is for. After deploy OK, point the user at the right command depending on the framework choice:

| Framework | Command (run from project root) |
|---|---|
| Next.js | `npx create-next-app@latest clients/web` |
| Vite + React/Vue/Svelte | `npm create vite@latest clients/web` |
| Express (backend) | `npm init -y && cd backend && npm install express` |
| Fastify (backend) | `npm create fastify@latest backend` |
| FastAPI (backend) | `cd backend && uv init && uv add fastapi uvicorn` |
| Django | `cd backend && uv init && uv add django && uv run django-admin startproject app .` |
| Hono (backend) | `npm create hono@latest backend` |

For frameworks not listed, ask the user which official scaffolder they prefer and point them at it. Never invent a backend skeleton — the framework's own tooling is always more accurate and up-to-date.

Wait for the user to confirm script success before proceeding to step 6.

## 6. Fill in placeholders

Now `.claude/`, `CLAUDE.md`, and `CHANGELOG.md` exist in the project. Edit them with the `Edit` tool — no shell needed.

### CLAUDE.md

Replace, using detected or interviewed values:
- `{{PROJECT_NAME}}` → directory name (or name from package.json / pyproject.toml).
- `{{LANGUAGE}}`, `{{LANGUAGE_VERSION}}`, `{{FRAMEWORK_OR_KEY_LIBS}}`, `{{RUNTIME_OR_TOOLING}}`, `{{DATABASE_OR_NONE}}`.
- `{{INSTALL_CMD}}`, `{{DEV_CMD}}`, `{{BUILD_CMD}}`, `{{TEST_CMD}}`, `{{LINT_CMD}}`, `{{TYPECHECK_CMD}}`, `{{FORMAT_CMD}}`.
- `{{MCP_SECTION}}` → bulleted list of selected MCPs with their purpose, or `<none configured>`.
- `{{SERENA_BLOCK}}` → **if the project uses Serena** (the deploy ran with `--serena`), paste the "When to prefer Serena tools" + "Graphify" sections that follow it in the template, as PLAIN TEXT outside any comment, and delete the commented source block. **Otherwise**, delete both the placeholder line and the commented source block. This matters: block-level HTML comments are stripped before CLAUDE.md reaches the model, so guidance left inside one is invisible in every deploy — Serena or not.

For any command that does not apply, write `<not configured>` with an HTML comment `<!-- TODO: configure ... -->`.

### docs/conventions.md

One placeholder to fill, since this file is copied verbatim by the deployer:
- `{{WORKING_LANGUAGE}}` → the language the user actually works in (ask if it is not obvious from the conversation; the conventions themselves are language-neutral, only this line is per-user).

**Leave the remaining `<!-- ... -->` blocks intact** — they are guides for the user to fill in WHY and Don't manually. (The `{{SERENA_BLOCK}}` source block above is the one exception: it is either promoted to plain text or removed.)

**`## WHAT — Structure` section:**
- If the project is **Fullstack** (or the user opted into the convention), replace the example comment block with the `backend/` / `clients/{web,ios,android,…}/` / `deploy.sh` / `scripts/` / `.env` layout documented in `references/stack-interview.md` ("Fullstack layout convention").
- For other project types, fill in the actual repo layout (or leave the example comment for the user to complete).

**`## WHAT — Deployment` section (new):**
If the user answered the deployment interview, insert a new `## WHAT — Deployment` section right after `## WHAT — Structure` summarizing hosting model, reverse proxy, TLS, and secrets. See `references/stack-interview.md` §2c for the format. If the project is not deployed (CLI tool, library), skip this section entirely.

**`## WHAT — Versions` section (new):**
Insert right after `## WHAT — Stack`. Populate from the detection + interview in `references/stack-interview.md` §2d: runtime, package manager, DB engine, backend framework, client frameworks, Docker base images. Omit bullets for categories that don't apply.

### .claude/settings.json

The project's `.claude/settings.json` is a **minimal stub** — the base
permissions, hooks, attribution, and bypass lockdown are CENTRAL (installed in
`~/.claude/settings.json` from the dotclaude repo) and apply to every project
automatically. Permissions and hooks **merge** across scopes, so the project
stub only **adds** what is specific to this project; it never re-declares the
base config and there is no `{{SCRIPT_EXT}}` placeholder anymore.

Only edit the project stub if this project needs something project-specific:

- **MCP tool permissions:** add `mcp__<server>__*` to `permissions.allow` for
  each MCP the user selected. Note: selecting Serena deploys a **two-server
  bundle** (Serena + Graphify), so add **both** `mcp__serena__*` and
  `mcp__graphify__*` when Serena was chosen. Selecting the Xcode MCP adds
  `mcp__xcode__*`; selecting Playwright (`--ui`) adds `mcp__playwright__*`.
- **SQL client (if a SQL stack was detected):** add `Bash(psql:*)` and/or
  `Bash(sqlite3:*)` to `permissions.allow` (on Windows the user is on the
  central PowerShell config, so add `PowerShell(psql *)` / `PowerShell(sqlite3 *)`).

If the project needs nothing project-specific, leave the stub's empty
`allow`/`ask`/`deny` arrays as they are. Do NOT copy the central hooks or the
base permission rules into it by hand — they already apply from `~/.claude/`.
(The **one** hook block that legitimately lives in the project stub is Serena's
drift-prevention hooks, but you never write those by hand either —
`init.sh --serena` merges them automatically when Serena is deployed. See
`references/mcp-and-db.md`.)

> The OS split (`.sh` vs `.ps1` hooks, the PowerShell mirror of the permission
> rules) is handled once by `install.sh`/`install.ps1` when they write
> `~/.claude/settings.json`, not per project. This skill no longer touches it.

## 7. .gitignore sanity check

Read `.gitignore` and confirm it excludes `.claude/settings.local.json`. The merged file from the deploy should already have it — if not, append the line.

Remind the user:
- `.claude/settings.json` (the per-project stub) and `settings.local.json.example` ARE committed; `.claude/settings.local.json` is gitignored (personal overrides). The hooks/agents/skills/rules/output-styles are central in `~/.claude/`, not in the project.
- `CLAUDE.md` and `CHANGELOG.md` are committed.
- `docs/` IS committed — it is the portable contract of the project (see `docs/README.md`). The template seeds `docs/backend.md` (API), `docs/ui.md` (design tokens + sections), `docs/user-stories.md` (what the user can do), and `docs/conventions.md` (how to write the code — a portable mirror of the central rules for editors without Claude Code); the user fills them and runs `/update-docs` whenever a contract or rule changes. Each doc is self-maintained.

## 7b. Branch workflow preference

The central `guard-push-main` hook is always on: it blocks force push (always) and direct pushes to `main`/`master` (configurable). By default it assumes **branching** — `feature/*` and `fix/*` branches, merged to main via PR. If the project will live entirely on main (solo project, prototype, scratch repo), the main-push block gets in the way.

**Ask via AskUserQuestion:**

- "How will you work with git in this project?"
  - **Branches (Recommended)** — `feature/*`, `fix/*`, merge to main via PR. The `guard-push-main` hook protects you from pushing to main by mistake.
  - **Everything on main** — solo or scratch project. `"allowPushToMain": true` will be written into `.claude/settings.local.json` (gitignored). Force push stays blocked.

**If they answer "Everything on main"**, use `Read` + `Write` (or `Edit` if it already exists) on `./.claude/settings.local.json`:

- If the file does NOT exist: create it with `{ "allowPushToMain": true }`.
- If it DOES exist: read it, parse the JSON, add/update `"allowPushToMain": true` preserving every other field, and rewrite. **Never delete existing fields.**

**If they answer "Branches"**, don't touch `settings.local.json`. The hook is already active by default.

**On a re-run**: if `settings.local.json` already defines `allowPushToMain`, respect the earlier decision; only ask if the field does not exist yet.

## 8. Verify end-to-end

Use the regular `Bash` tool (a non-zero exit there is informative, not fatal):

- `python3 -m json.tool .claude/settings.json >/dev/null` — confirms JSON parses (mirrors `install.sh`; the repo avoids `jq` — see DESIGN.md §5).
- `ls .claude/` — should show only the per-project files: `settings.json` and `settings.local.json.example`. The hooks/agents/skills/rules/output-styles are CENTRAL (`ls ~/.claude/` to see them) and are NOT copied into the project.
- `ls CLAUDE.md CHANGELOG.md` — both must exist.
- `ls docs/` — `README.md`, `backend.md`, `ui.md`, `user-stories.md`, `conventions.md` must exist (seeds for the portable contract surface).
- If the user picked "Everything on main" in §7b: `python3 ~/.claude/skills/init-project/scripts/detect-drift.py` should report `ALLOW_PUSH_MAIN=TRUE`. (Inline `python3 -c` is blocked by the central `guard-destructive` hook — the checks live in that script.)

Summarize to the user what was deployed.

## 9. Next steps for the user

Tell the user literally:

1. **Open a new session** in this project so Claude loads the deployed `.claude/` plus the central `~/.claude/` config.
2. **Fill in WHY and Don't** in CLAUDE.md when you discover architectural decisions.
3. **Commit the per-project files** (`.claude/settings*.json`, `CLAUDE.md`, `docs/`) so the project carries its own context.
4. **Use `/compound`** when I make a systematic mistake — it codifies the fix (central artifacts update every project via `git pull && ./install.sh`).
5. **Use `/resume-context`** at the start of each new session on this project.
6. **(Optional) Enable the `dotclaude` output style** via `/config` → Output style → `dotclaude` to apply the tone/language conventions at the system-prompt level. Per-machine choice; the same conventions already apply as an always-on rule without it.

**If Serena/Graphify was deployed (`--serena`)**, also tell the user:
- Serena's drift-prevention hooks AND Graphify's graph-first nudge (`prefer-graphify`) are already merged into `.claude/settings.json` (init did this) — nothing to run.
- `init.sh --serena` also ran `graphify hook install` for you (git post-commit auto-rebuild). The **one** step left is to build the graph once: run `/graphify .` in the project (the `graphify` MCP server stays unavailable until then). Do NOT run `graphify install` — see `references/mcp-and-db.md` §3. (If `graphify` was missing from PATH at deploy, `uv tool install graphifyy` first.)

`/init-project` only deploys the per-project base; the reusable core is central. Add project-specific skills, agents, rules over time in the project's own `.claude/` (they ADD to the central ones). See `~/.claude/templates/project/README.md`.
