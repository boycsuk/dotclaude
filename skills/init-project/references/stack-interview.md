# Reference: stack interview (§2, §2b, §2c, §2d)

Loaded by `SKILL.md` step 2 on a first-time deploy (or the Reconfigure path).
Covers stack detection/interview, Docker, deployment target, and version
pinning. The §0 description (if the user gave one) biases the option order and
labels in every AskUserQuestion here — mark the recommended option `(Recommended)`
and put it first, but never remove the others. Question and option copy below is
written in English; present it to the user in Castilian Spanish per the
conversation-language rule.

## 2. Detect stack or interview

### Case A: stack is detectable

If any of these files are present, infer from them:
- `package.json` → Node/TypeScript. Read `engines.node`, `dependencies` for framework, `scripts` for commands.
- `pyproject.toml` / `requirements.txt` → Python. Read python version, deps for framework.
- `Cargo.toml` → Rust. Read `package.rust-version` if present, deps for framework.
- `go.mod` → Go. First line has the Go version.
- Lockfiles indicate the package manager.

For commands: read `scripts` from package.json, targets from Makefile, sections `[tool.*]` from pyproject.toml.

**If anything is ambiguous, ask via AskUserQuestion before filling in.**

### Case B: empty or unrecognized project

Run an interview using AskUserQuestion. Ask in this order:

1. **Main language**: TypeScript / Python / Rust / Go / Java / C# / Other
2. **Framework/runtime**: depends on the language chosen
3. **Package manager**: npm / pnpm / yarn / poetry / uv / pip / cargo / go modules / maven / nuget
4. **Database**: PostgreSQL / MySQL / MongoDB / SQLite / Redis / None
5. **Project type**: API / Frontend / Fullstack / CLI / Library / Script

Use canonical commands for the chosen stack. Mark inapplicable commands as `<not configured>`.

### Fullstack layout convention

If the project type is **Fullstack** (Case B step 5) — or if you detect that an existing project mixes a backend and one or more clients but has not yet committed to a layout — propose this directory structure and write it into the deployed CLAUDE.md `## WHAT — Structure` section:

```
<project root>/
├── backend/                  # API / server code
├── clients/                  # one subfolder per client surface
│   ├── web/                  # web frontend
│   ├── ios/                  # native iOS app (if applicable)
│   ├── android/              # native Android app (if applicable)
│   └── <other>/              # desktop, CLI client, etc.
├── deploy.sh                 # lifecycle: start | stop | restart | logs (mode from APP_MODE)
├── scripts/                  # project automation (db seed, migrations, codegen, ...)
├── .env                      # gitignored — local secrets only
└── .env.example              # committed — documents required variables
```

**How to apply it:**

- **Existing project that already matches:** confirm and document it. Do not move files around.
- **Existing project with a different layout** (e.g. `apps/web` + `apps/api`, or backend at the root with a `frontend/` sibling): tell the user the convention and ask whether they want to migrate or keep their current layout. **Do not move files without explicit confirmation** — that is a high-impact change that deserves its own session, not a side effect of `/init-project`.
- **Empty project:** ask whether to create the directories now. If yes, after the deploy step the user runs `mkdir -p backend clients/web scripts`; the skill itself does not create them (no shell side effects beyond `init.sh`).

In all cases, ensure `.env` is in `.gitignore` (the template's `.gitignore` already excludes it) and prompt the user to also commit a `.env.example`.

## 2b. Detect or ask about Docker

Docker changes how commands are run — `docker compose exec <service> <cmd>` instead of running the binary directly on the host.

**Detection signals (use the regular Bash tool):**

`ls docker-compose.yml docker-compose.yaml compose.yml compose.yaml Dockerfile`

If any of these are present, Docker is in use. Read `docker-compose.yml` (or equivalent) and note service names — typical names: `app`, `web`, `api`, `db`, `postgres`, `mysql`, `redis`.

**If no Docker files are detected**, ask via AskUserQuestion:
- "Will this project use Docker or Docker Compose?"
  - Yes — Docker Compose from the start
  - Yes — Dockerfile only (no compose)
  - No

If yes (either flavor), ask a follow-up about which services run containerized: app, db, both, or other. If the database was identified in step 2, ask specifically whether it runs in Docker (this drives the db client commands in §4).

**If Docker is in use**, when filling commands in step 6 prefix runtime commands with `docker compose exec <service>`:
- `{{DEV_CMD}}` → `docker compose up` (or `docker compose up -d && docker compose logs -f app` for detached).
- `{{TEST_CMD}}` → `docker compose exec <app-service> <test-runner>` (e.g. `docker compose exec app npm test`).
- `{{LINT_CMD}}`, `{{TYPECHECK_CMD}}`, `{{FORMAT_CMD}}` → same prefix.
- `{{INSTALL_CMD}}` typically stays on the host (it's `docker compose build` or runs before `up`).
- `{{BUILD_CMD}}` → `docker compose build` for image rebuilds.

Document the service names in the deployed CLAUDE.md `## WHAT — Stack` section so future sessions know which service to `exec` into.

## 2c. Deployment target

How the project is deployed shapes a lot: reverse proxy config, TLS, where secrets live, how logs are read, what `./deploy.sh` should do. Ask via AskUserQuestion in order. **Skip every question below if the user answers "No deployment" to the first one** (CLI tools, libraries, scripts).

### Question 1: Hosting model

- "How will this project be deployed?"
  - **VPS / dedicated server** (DigitalOcean, Hetzner, bare-metal, etc.) — long-running process on a Linux box.
  - **Container platform** (Fly.io, Railway, Render, ECS, Kubernetes) — image pushed to a registry, orchestrator handles uptime.
  - **Serverless** (Vercel, Netlify, Cloudflare Workers, AWS Lambda) — function-per-request, no persistent process.
  - **No deployment** — CLI tool, library, local script.

### Question 2: Reverse proxy (only if VPS or container platform)

- "Which reverse proxy will handle the HTTP traffic?"
  - **Caddy** — automatic HTTPS via Let's Encrypt, simple `Caddyfile` syntax.
  - **nginx** — classic, requires manual cert renewal (certbot) or in front of a TLS terminator.
  - **Traefik** — dynamic config from Docker labels, popular with container orchestrators.
  - **None / platform handles it** — the platform (Fly, Railway, Vercel...) terminates TLS upstream.

### Question 3: TLS / certificates (only if reverse proxy is Caddy / nginx / Traefik)

- "How are TLS certificates managed?"
  - **Let's Encrypt automatic** — handled by Caddy or Traefik out of the box, certbot for nginx.
  - **Cloudflare proxied** — Cloudflare terminates TLS at the edge, origin uses self-signed or Cloudflare Origin CA.
  - **Manual / corporate CA** — certs provisioned externally and dropped in a known path.

### Question 4: Secrets management (only if deployment is yes)

- "Where do production secrets live?"
  - **`.env` file on the server** — plain file outside the repo, loaded by the app or systemd `EnvironmentFile=`.
  - **Vault / secrets manager** — Hashicorp Vault, AWS Secrets Manager, Doppler, Infisical.
  - **CI/CD injected** — GitHub Actions / GitLab CI secrets pushed to the platform at deploy time.
  - **Platform-native** — Fly secrets, Railway variables, Vercel env config.

### What to write in the deployed CLAUDE.md

Add a new section `## WHAT — Deployment` summarizing the answers. Example for a Caddy + VPS + Let's Encrypt + .env setup:

```
## WHAT — Deployment
- Hosting: VPS (Hetzner, Ubuntu 22.04)
- Reverse proxy: Caddy (Caddyfile in repo root, deployed to /etc/caddy/Caddyfile)
- TLS: Let's Encrypt automatic via Caddy
- Secrets: /etc/<project>/env loaded as systemd EnvironmentFile
- Bring-up: ./deploy.sh {start|stop|restart|logs} (APP_MODE in .env lets `start` branch dev vs prod; fill the function bodies for this project's runner)
```

Adapt the bullets to the user's answers. If Caddy was chosen, also remind the user to commit a `Caddyfile` at the repo root with the basic reverse-proxy block — the skill does not create it but flags it as a TODO. Same for nginx (`nginx.conf`), Traefik (labels in `docker-compose.yml`).

`./deploy.sh` at the repo root is the natural home for the actual bring-up logic — it's the project's primary command, so it sits at the top level. `scripts/` is reserved for secondary automation (seed, migrations, codegen). The `--deploy-script` flag writes a **skeleton** (the `.ps1` variant on Windows) that accepts four subcommands:

- `./deploy.sh start` — bring the app up (defaults to `start` with no argument).
- `./deploy.sh stop` — bring it down.
- `./deploy.sh restart` — `stop` then `start`.
- `./deploy.sh logs` — follow logs.

The skeleton wires up the subcommand dispatch and reads `APP_MODE` from `.env` (so `start` can branch dev vs prod), but the **bodies of `start`/`stop`/`logs` are left empty with a TODO and commented examples** (Docker Compose, a Node/Python process, a compiled binary, a systemd/Windows service). The user fills in the one that matches the project — the scaffold gives the structure, not a Docker assumption. After deploy, point the user at the TODOs in `deploy.sh`/`deploy.ps1` and suggest the runner that fits their stack (e.g. Docker if `--compose` was used).

## 2d. Pin versions for every service

Concrete versions matter for two reasons: (1) Claude's training data covers multiple major versions of every common tool, so without pins it will hallucinate APIs that don't exist in the user's version; (2) the `verify-on-edit` hook and CI/CD assume a specific runtime — a `python3` on the host that resolves to 3.10 will fail tests written for 3.13 walrus features.

**Detect first, ask only what you can't infer.** For each category below, try to read the version from project files; if nothing is found, ask via AskUserQuestion. Group related questions in a single AskUserQuestion call (up to 4 questions per call).

### Language runtime

| Source | Where to look |
|---|---|
| Node | `package.json` → `engines.node`, `.nvmrc`, `.node-version` |
| Python | `pyproject.toml` → `[tool.poetry.dependencies.python]` or `[project.requires-python]`; `.python-version` |
| Rust | `Cargo.toml` → `[package].rust-version`; `rust-toolchain.toml` |
| Go | `go.mod` first line |
| Java | `pom.xml` → `<maven.compiler.release>`; `build.gradle` → `sourceCompatibility`; `.sdkmanrc` |
| C# / .NET | `*.csproj` → `<TargetFramework>`; `global.json` |

If found, surface it ("Detected Node 22.11 from `.nvmrc` — keep this?") and let the user confirm or override. If not found, ask:

- "Which <language> runtime version?" — give 3-4 sensible options spanning the current LTS and the latest stable, plus an "Other" escape hatch.

### Database engine

If a SQL database was identified (step 2 or §4) **and** runs in Docker (step 2b), read the image tag from `docker-compose.yml` — `postgres:17.2`, `mysql:8.4`, etc. That is the source of truth, just confirm.

If the DB runs on the host or wasn't documented yet, ask:

- "Which <PostgreSQL / MySQL / MongoDB / Redis> version?" with current major versions as options (Postgres 17 / 16 / 15; MySQL 8.4 / 8.0; Mongo 8 / 7; Redis 7.4 / 7.2).

### Backend framework

Detect from dependencies:
- `package.json` → `next`, `express`, `fastify`, `hono`, `nestjs`, `koa`...
- `pyproject.toml` / `requirements.txt` → `fastapi`, `django`, `flask`, `litestar`...
- `Cargo.toml` → `axum`, `actix-web`, `rocket`, `tide`...
- `go.mod` → `gin`, `echo`, `chi`, `fiber`...

Show the detected version and let the user confirm or override. For empty projects, ask both framework AND version in a follow-up.

### Client / frontend frameworks

If the layout has `clients/` (Fullstack convention from §2) or detection found a frontend, pin the framework version per client:

- **Web client:** `package.json` → `next`, `nuxt`, `sveltekit`, `vite`, `react`, `vue`...
- **iOS client:** `Package.swift` Swift version; `Podfile` platform; `*.xcodeproj` deployment target.
- **Android client:** `app/build.gradle.kts` → `compileSdk`, `minSdk`, `targetSdk`; `gradle/libs.versions.toml`.

For empty `clients/` subdirectories the user planned in §2, ask which framework + version they intend.

### Package manager

Detect from lockfile presence:
- `package-lock.json` → npm
- `pnpm-lock.yaml` → pnpm (read `packageManager` field in package.json for exact version)
- `yarn.lock` → yarn
- `poetry.lock` → poetry
- `uv.lock` → uv
- `Cargo.lock` → cargo (version follows Rust toolchain)
- `go.sum` → go modules

For pnpm/yarn/poetry/uv, the `packageManager` field or `tool.poetry`/`tool.uv` block pins the exact version. Confirm it; if absent, ask the user to pick the latest stable.

### Docker base images (if step 2b said yes to Docker)

Read every `Dockerfile` and `docker-compose.yml` for `FROM` lines and `image:` fields. Each tag (`node:22-alpine`, `python:3.13-slim`, `postgres:17.2-bookworm`, `redis:7.4-alpine`) is a version pin. Surface them as a summary; ask the user to confirm or pick a stricter pin (`node:22-alpine` → `node:22.11.0-alpine3.20` for reproducibility).

### What to write in the deployed CLAUDE.md

Add a `## WHAT — Versions` section right after `## WHAT — Stack`, with one bullet per category. Example for a fullstack Node + Postgres + Next.js setup:

```
## WHAT — Versions
- Runtime: Node 22.11.0 (pinned in .nvmrc)
- Package manager: pnpm 9.12.3 (pinned in package.json `packageManager`)
- Database: PostgreSQL 17.2 (Docker image `postgres:17.2-bookworm`)
- Backend framework: Express 4.21
- Web client: Next.js 15.0 + React 19.0
- Docker base images: node:22-alpine, postgres:17.2-bookworm
```

For categories that don't apply (no DB, no client, no Docker), omit the bullet entirely — don't write `<not configured>`.

**Important:** the versions in CLAUDE.md must match what the project actually uses. If you ask the user to upgrade Postgres from 15 to 17 because "17 is current," that is a behavior change that belongs in a separate session with explicit confirmation. The init flow only documents what is there.
