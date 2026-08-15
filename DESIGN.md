# Design notes

Why this repo looks the way it does. Captured from the original design conversation so future sessions (or other people) can see the reasoning, not just the result.

This is not a changelog. It is the set of decisions that shape the architecture — what was considered, what was chosen, and why.

## Origin

The starting point was a 12-layer context engineering guide (kept locally, not in this repo) that summarizes the state of Claude Code best practices as of mid-2026. Core idea: the quality bottleneck has moved from prompt engineering to **context engineering**. The wins come from how you assemble CLAUDE.md, skills, hooks, sub-agents, and rules into a system that compounds with use — not from clever wording.

The goal of this repo: turn that guide into a concrete, portable, reusable setup. One install, every project starts with the right context.

## Key decisions

### 1. Template, not global config

**Considered:** putting everything in `~/.claude/` so it applies to all projects automatically.

**Chosen:** a portable `.claude/` template that deploys per project via `/init-project`, plus a minimal global layer.

**Why:** project-level config follows the project (commit, share with team, version with the codebase). Global config does not scale — every new project would inherit conventions that may not apply. Plus, the team that clones the repo inherits the same context.

> **Superseded in part by §23 (2026-05-30).** Real solo use showed the opposite pain: per-project copies meant a master-repo improvement reached no existing project without updating each by hand. The reusable artifacts (hooks, agents, skills, rules, output-styles) are now CENTRAL in `~/.claude/`; only CLAUDE.md/docs/settings-stub stay per-project. This reasoning still holds for what stays per-project. See §23.

### 2. Neutral skeleton with a planner skill, not pre-baked stack variants

**Considered:** separate templates per stack (`templates/python/`, `templates/typescript/`, etc.).

**Chosen:** one neutral template + a `/init-project` skill that detects the stack (or interviews the user) and fills placeholders in CLAUDE.md. See decision 15 for why the skill plans but does not execute the file copy itself.

**Why:** one source of truth. Pre-baked variants drift apart over time and duplicate work. The detection + interview pattern handles both existing projects (auto-detect) and empty ones (interview).

### 3. Progressive disclosure with `rules/`

**Considered:** dumping all conventions into a long CLAUDE.md.

**Chosen:** keep CLAUDE.md under 200 lines; extensive conventions live in `.claude/rules/<topic>.md` files. A rule with a `paths:` frontmatter field loads only for files matching its globs; a rule without `paths:` loads every session at the same priority as `CLAUDE.md`. The `description:` field does NOT gate loading (that is a skills concept) — only `paths:` does. Because `description:` is inert for rules, the rule files carry no `description:` at all; their frontmatter is either a bare `paths:` list (conditional) or absent entirely (always-on), with a maintainer note in an HTML comment below it (HTML comments are stripped before injection, so they cost no tokens).

**Why:** CLAUDE.md is always in context. Long rules dilute the signal. `code-quality.md` and `security.md` carry a `paths:` glob of source-file extensions so they load only when editing code; `workflow.md` and `ai-collaboration.md` are not cleanly globbable (they apply to commits and every session respectively) so they stay always-on but are kept short. Security is deliberately globbed broadly (all source extensions, not just backend/auth) because it is transversal and a narrow glob would silently skip files that touch I/O. Net effect: the file-type-specific bulk loads only when relevant; better signal-to-noise without pretending every rule is conditionally loaded.

**Caveat (tool bug, not design):** path-scoped rules inject when Claude **reads** a matching file, not when it **creates** one — see anthropics/claude-code#23478. So a path-scoped rule does not fire on the Write that creates a brand-new matching file. For `code-quality.md` this is mitigated by its own "read 2-3 sibling files first" rule (reading a sibling pulls the rule in before the write); for `security.md` the residual risk is that net-new auth/I/O files written from scratch without reading a sibling may not see the rule. Keeping the glob broad rather than narrow minimizes the surface where this matters. Quote all glob patterns (unquoted YAML globs with `*`/`{` can silently fail — see #17204).

### 4. Hooks in both Bash and PowerShell

**Considered:** Bash-only (require Git Bash on Windows) or Python-only (universal).

**Chosen:** `.sh` and `.ps1` siblings. `/init-project` picks the right variant based on detected OS.

**Why:** native Windows users without WSL exist. Forcing Git Bash adds friction. Python would work but adds a runtime dependency the hook scripts do not need. Two variants is a small maintenance cost (rule: edit both together, documented in `templates/project/README.md`).

### 5. Hook json parsing without `jq`

**Considered:** using `jq` (the usual choice for shell JSON).

**Chosen:** `python3 -c "import json; ..."`.

**Why:** `jq` was missing on the test machine. Python 3 is present on virtually every Linux/macOS/WSL install. Removing the dependency made the hooks immediately portable. PowerShell variant uses native `ConvertFrom-Json`.

**This licence covers hooks only — never skills (learned 2026-07-26).** A hook runs *as* the PreToolUse layer, so nothing intercepts it. A skill's commands go through that layer like any other Bash call, and `guard-destructive` blocks inline interpreters. `/init-project` had four inline `python3 -c` drift checks that silently died with exit 2 once §9 hardened the guard — the `--update` Serena/Graphify reconciliation was inoperative for two commits and nobody noticed, because a skill that gets exit 2 just improvises. Skill-side logic that needs Python goes in a **script file** (`skills/init-project/scripts/detect-drift.py`), which the guard allows. `check.py` enforces this: it fails on any inline interpreter under `skills/` or `global/.claude/skills/`.

### 6. Compound engineering as first-class

**Considered:** treating "capture learnings" as a manual discipline.

**Chosen:** a dedicated `/compound` skill that asks where a learning belongs (CLAUDE.md / skill / hook / rule / agent) and applies it.

**Why:** the most-cited practice in 2026 Claude Code lore. Without an explicit prompt, learnings get lost between sessions. The skill makes the placement decision explicit so corrections actually accumulate.

### 7. Model selection: `inherit` by default, Haiku only for mechanical work

**Considered:** assigning specific models everywhere, or leaving everything to inherit.

**Chosen:** override to Haiku only on truly mechanical components (`verify`, `changes`, `resume-context`). Everything else `inherit`.

**Why:** Haiku is fast and cheap but degrades on tasks needing judgment. Forcing Opus anywhere is wasteful — if the session is on Opus, `inherit` already uses it. The override is restricted to tasks where the worst outcome is a slightly worse phrasing, not a missed bug. Documented in `templates/project/README.md` under "Model selection policy".

`/update-docs` (decision 17) deliberately inherits — judging whether a diff is a contract change, and how to phrase a new endpoint entry, is reasoning work, not pattern matching.

`researcher` was originally Haiku (treated as mechanical lookup), but that overlapped with the built-in **Explore** agent (also Haiku, read-only). It was re-scoped to architectural *synthesis* — end-to-end flow, cross-module dependencies, seams — which is reasoning work, so it now `inherit`s. Quick "where is X" lookups are explicitly delegated to Explore; the custom agent earns its keep only on the synthesis tasks Explore does not do.

**Reasoning effort (added 2026-07-26):** agent frontmatter also supports `effort` (`low`/`medium`/`high`/`xhigh`/`max`), orthogonal to `model` and inheriting the session's level by default. Same policy, opposite direction: `researcher`, `debugger`, and `code-reviewer` pin `effort: high`, because their failure mode is a missed bug or a shallow root cause — a session running at low effort would silently degrade exactly the work whose value is depth. `db-inspector` inherits both knobs: its safety layer is rule-based (denylist, not reasoning), and interpreting results should track the session's judgment level. The Haiku-pinned mechanical skills get no effort override.

### 8. Trans-project preferences live in `rules/`, not global

**Considered:** keeping personal preferences (no emojis, never agree just to be agreeable, cite sources) in the global CLAUDE.md.

**Chosen:** move them to `rules/ai-collaboration.md` and `rules/workflow.md` so every project that uses the template inherits them.

**Why:** these rules describe how Claude should behave when working on any project. A teammate cloning the repo benefits from the same baseline. Keeping them global would mean every collaborator has to set them up independently. What stays in global CLAUDE.md is genuinely personal: research source hierarchy, explanation style, project setup workflow.

### 9. Permissions: balanced default with explicit deny for destructive actions

> **Superseded in part by the 2026-07-09 revision below** — the granular allowlist
> the "Chosen"/"Why" prose describes was replaced by allow-by-default Bash + a
> hardened safety net. Read the revision note before treating the original prose as
> current.

**Considered:** strict (ask for almost everything) or permissive (allow everything, rely on user oversight).

**Chosen:** allow common read/edit/inspect operations, `ask` for impactful operations (push, dep installs, settings edits), `deny` for genuinely destructive ones (`rm -rf`, force push, `git reset --hard`, `.env` reads, `sudo`).

**Why:** strict creates friction on every benign action and trains the user to approve blindly. Permissive removes the safety net. Balanced lets routine work flow while keeping a real gate on irreversible operations.

> **Revised (2026-07-09) — allow-by-default Bash + hardened safety net.** The granular
> read-only `Bash(...)` allowlist never converged: every new tool (cargo, docker
> compose, jq, …) meant another prompt, another entry. Per the official docs'
> recommended pattern ("add `Bash` to your allow list and register a PreToolUse hook
> that rejects the commands you want blocked"), `allow` is now `["Bash", …tools]` and
> the *deny list + `guard-destructive` hook are the safety net*. This is only safe
> because the permissive model §9 originally rejected ("removes the safety net") no
> longer applies: `guard-destructive` now matches **all** Bash (not just `rm -rf` /
> `git reset --hard`) and additionally blocks the two vectors a `deny` list can't catch
> by argument — remote code execution (`curl … | sh`, `wget … | bash`) and inline
> interpreters (`python3 -c`, `node -e`, `bash -c`). `ask` rules (push, dep installs,
> `chmod`/`chown`) still fire because ask is evaluated before allow. Net effect: routine
> work runs silently, the irreversible/RCE gate stays deterministic. The `curl`/interpreter
> blocks live in the hook, not `deny`, precisely because the docs warn arg-scoped `deny`
> rules are bypassable (§10's determinism rationale). Tested: 20/20 block/allow cases.

**Windows / PowerShell mirror.** Permission rules are matched against the tool that ran the command. On native Windows the command tool can be `PowerShell` (the default for Bedrock/Vertex/Foundry users, or when `CLAUDE_CODE_USE_POWERSHELL_TOOL=1`), so `Bash(...)` rules never match there. The versioned `settings.json` stays `Bash`-scoped (correct and idempotent for the Linux/macOS/WSL majority); `/init-project` mirrors the deny/ask/allow rules to `PowerShell(...)` when it deploys on Windows (`SCRIPT_EXT=ps1`). PowerShell rules use the same shape as Bash rules and canonicalize aliases (`Remove-Item` matches `rm`/`del`/`rmdir`, `Get-ChildItem` matches `ls`/`dir`/`gci`). Without this mirror the deny-first guarantee silently evaporates on Windows — exactly the failure §10's determinism is meant to prevent. Requires Claude Code ≥ 2.1.147 for the `PowerShell(...)` hook `if` form.

**Bypass mode.** `--dangerously-skip-permissions` (`bypassPermissions`) skips the entire allow/ask/deny gate and all PreToolUse guard hooks (only `rm -rf /` and `rm -rf ~` remain as circuit breakers). The template sets `permissions.disableBypassPermissionsMode: "disable"` in the deployed `settings.json` to close that hole. It works from any settings scope (not just managed). There is no `"enable"` override — the opt-out is to remove the line from the versioned `settings.json`. Auto mode is deliberately NOT disabled by default (it runs background safety checks and still honors deny/ask rules and blocking hooks); `disableAutoMode` is offered as a commented opt-in in `settings.local.json.example`.

### 10. Hooks: deterministic guarantees, not prompts

**Considered:** putting "never push to main" as a rule in CLAUDE.md.

**Chosen:** hooks that exit 2 with stderr to Claude. The action is blocked, not requested-not-to-happen.

**Why:** rules in CLAUDE.md are advisory (~80% obeyed). Hooks are 100% deterministic. For non-negotiable safety (no `rm -rf /`, no force push to main, no secret leaks), advisory is not enough. Tested with 21+9+8 cases — false positives are rare and tunable.

### 11. Global settings minimized

**Considered:** keeping the global `~/.claude/settings.json` with the default permissions Claude Code installs.

**Chosen:** strip global settings to just account-level configuration (`effortLevel`, `agentPushNotifEnabled`, `enabledPlugins`) and the `additionalDirectories` grant needed for plugins. All permissions and hooks come from the project's `.claude/settings.json` deployed by the template.

**Why:** consistency with the "everything project-level" philosophy. Trade-off: working in a directory without `/init-project` deployed means more permission prompts. That is intentional friction — pushes me to use the template instead of working in unconfigured directories.

> **Reversed by §23 (2026-05-30).** The centralization makes `~/.claude/settings.json` the home of the base permissions + hooks (merged non-destructively with the user's own keys), exactly the opposite of "minimized". The friction this decision accepted (unconfigured dirs prompt more) is now the *feature*: the central config makes every directory configured. See §23.

### 12. Match existing conventions with an escape clause

**Considered:** a strong "match the existing style" rule alone.

**Chosen:** the rule in `code-quality.md` paired with an explicit escape clause: do NOT replicate the pattern if it is genuinely harmful (security flaw, anti-pattern in the project's `Don't` section, broken type safety). The matching operational step lives in `workflow.md`.

**Why:** without the escape clause, the rule perpetuates tech debt. Without the rule, every new file fragments the codebase style. The pair (what + how, with safety valve) is the durable formulation.

### 13. Serena MCP as an opt-in symbol-level layer

**Considered:** (a) baking Serena into the default template so every project gets it; (b) leaving it as a third-party tool the user wires up manually; (c) opt-in via `/init-project` with a pre-built `.mcp.json` template.

**Chosen:** option (c). The skill offers Serena in the MCP multi-select; when selected, it merges the `serena` + `graphify` fragments from `templates/project/mcp/` into the project's `.mcp.json`, adds `mcp__serena__*` to `permissions.allow`, gitignores `.serena/project.local.yml` and `.serena/cache/`, and includes a Serena block in CLAUDE.md explaining when to prefer its tools.

**Why opt-in, not default:** Serena requires `uv tool install serena-agent` once per machine — a hard prerequisite the template cannot guarantee. Forcing it on every project would break `/init-project` for users who don't have `uv`. Making it opt-in keeps the default deploy zero-dependency.

**Why `uv tool install` instead of `uvx --from git+...`:** the `uvx` form works without a permanent install but pays ~5–15s of startup latency per session and re-resolves the package on cold starts. `uv tool install` pins the version, starts instantly, and matches Serena's own official recommendation. The trade-off (one extra one-time setup command) is paid once and amortized across every project that opts in.

**Why a separate `.mcp.json` file instead of merging into `settings.json`:** Claude Code reads MCP servers from `.mcp.json` (committed, team-wide) by convention. Putting Serena there keeps the team-shared MCP config separate from per-user permissions, and the file is small enough that it's clearer as a dedicated artifact than as a nested block.

**Companion: Graphify in the same bundle.** `--serena` deploys two servers, not one — Serena (symbol-level) plus [Graphify](https://github.com/safishamsi/graphify) (graph-level: a queryable knowledge graph of code+docs+schema). They are genuinely complementary — Serena acts precisely on a known symbol, Graphify answers structural/impact questions ("what depends on this", "what breaks if I change X") — so pairing them in one opt-in is higher-value than either alone, and they share the **same `uv` prerequisite** (Graphify installs via `uv tool install graphifyy`), so opting into Serena adds no new class of host dependency. Two asymmetries shaped the integration: (1) Graphify is *primarily a Skill* (`/graphify .`) with the MCP server as a secondary interface, so the recommended flow is build-the-graph-first, MCP-for-repeated-access second; we document the `/graphify .` build step rather than vendoring the skill's `SKILL.md` (Graphify's own CLI owns that, and copying it would rot). (2) The MCP server reads a *pre-built* `graphify-out/graph.json` and **fails to start until `/graphify .` has run once** — so unlike Serena it is inert on a fresh project. That's why `--serena` treats `serena` as a hard prerequisite (exit 4) but `graphify` as a soft one (warn only): a missing/never-built Graphify must not block deploying Serena, and Claude Code starts each MCP server independently so Graphify's absence does not affect Serena. `graphify-out/` is gitignored as build output.

**Why the `graphify` MCP server is launched via `uv run`, not `python -m`.** `graphifyy` installs into an *isolated* uv tool environment, so the system `python`/`python3` cannot import `graphify` — and on many hosts `python` (without the `3`) does not exist at all (verified: this dev machine has only `python3`, which still can't see the isolated package). A `"command": "python", "args": ["-m", "graphify.serve", …]` entry therefore fails to start the server silently. The README-canonical form `uv run --with graphifyy --with mcp -m graphify.serve graphify-out/graph.json` resolves the package on demand in an ephemeral env and works regardless of the host's Python layout. This reuses the **same `uv` prerequisite** the bundle already requires (both servers install via `uv`), so it adds no new dependency class. **Do not "simplify" this back to `python -m`** — it looks cleaner but is the broken form.

**Why deterministic hooks on top of the prose (Serena), and why the project stub.** Serena's CLAUDE.md/rules prose is *advisory* — it decays under context compaction, the "agent drift" failure Serena's own maintainers document (oraios/serena #1201: over a long session the model "forgets" and falls back to Grep/Edit). So `--serena` also merges Serena's official drift-prevention hooks into the project's `.claude/settings.json`: `serena-hooks activate` (SessionStart) and `serena-hooks remind` (PreToolUse, fires *only* when the model over-relies on grep/read without a recent Serena call — silent when compliant), plus `serena-hooks auto-approve`. This is the *hard* layer the prose can't be. The hooks live in the **project stub, not central `~/.claude/`**, because they invoke the `serena-hooks` binary, which only exists where Serena was installed — central would error/noise in every Serena-less project. We did **not** adopt Serena's `print-cc-system-prompt-override` (a complete ~8KB system prompt that would clobber the `dotclaude` output style and only applies via a launch flag a template can't deploy), nor `deny`-ing Grep/Edit (breaks the legitimate built-in uses Serena itself carves out for markdown/config/one-off reads). The hook source of truth is `templates/project/.claude/serena-hooks.json`; `init.sh`/`init.ps1` merge it idempotently (de-dup by command) and non-destructively.

**The gap `remind` leaves open, and our own hook that closes it (`prefer-serena-bash`).** Serena's `remind` only watches `Grep`/`Read` in the **main thread**. Two routes slip past it: (a) `sed`/`cat`/`head`/`tail`/`awk`/`grep` *inside* a `Bash` call — text-scanning a code file without ever touching the `Read`/`Grep` tools `remind` keys off; and (b) **sub-agents**, including the built-in `Explore` agent (which skips `CLAUDE.md` but, crucially, NOT `settings.json` `PreToolUse` hooks). In practice this is where `sed`/`cat` over source files crept back in during a long workflow audit. The fix is a single `PreToolUse` hook on the `Bash` tool — `prefer-serena-bash.{sh,ps1}` — because a `Bash` `PreToolUse` hook reaches both the main thread and every sub-agent at once. It is **ours, not Serena's** (Serena's `serena-hooks` binary is opaque and can't be extended), so it ships in `global/.claude/hooks/` like our other guard hooks, but is wired *only* through `serena-hooks.json` so it lands solely in `--serena` projects (nudging toward Serena where Serena isn't installed would be noise with no resolution). It is a **non-blocking nudge** (exit 0, delivered via `hookSpecificOutput.additionalContext` on stdout — see the 2026-08-15 revision in §17: the original stderr form never reached the model at all), mirroring `remind`'s "silent when compliant" contract: it fires only when the command reads a file with a *source* extension (config/doc/data files — `.md`/`.json`/`.yaml`/`.env`/`.log` — and vendored/build dirs are excluded, so legitimate reads stay silent), and skips writes (`cat >`, heredocs). We chose nudge over a hard `exit 2` block for the same reason §13 rejects `deny`-ing Grep/Edit: a block frustrates the legitimate raw-byte reads (a diff, a non-symbol slice) Serena itself carves out. Because the command path differs by OS (`.sh` vs `.ps1`) but `serena-hooks.json` is OS-agnostic and merged literally, the JSON carries a `{{HOOK_EXT}}` placeholder that `init.sh` resolves to `sh` and `init.ps1` to `ps1` just before the merge.

**Graphify gets the same determinism through OUR OWN hook, not its installer (revised 2026-07-09).** The earlier design ran `graphify install`, which self-registers two `PreToolUse` hooks. We stopped doing that: `graphify install` (and `graphify claude install`) also appends a raw `## graphify` block to `CLAUDE.md` and drops a per-project skill, and it *rewrites* `settings.json` destructively — in one project it clobbered Serena's own hooks. So instead we ship `prefer-graphify.{sh,ps1}` in `global/.claude/hooks/` (same pattern as `prefer-serena-bash`): a non-blocking `PreToolUse` nudge on `Bash` + `Read|Glob|Grep` that points at `graphify query` when a code file is grepped/read while `graphify-out/graph.json` exists — gated on the graph, so silent in Serena-only projects. It is wired through `serena-hooks.json` (merged by `--serena`), and `init.sh`/`init.ps1 --serena` run `graphify hook install` (git post-commit auto-rebuild, AST-only) so the graph never goes stale — the main reason the graph-first workflow gets abandoned. The graph itself is still built once by the user with `/graphify .`. This inverts the old asymmetry note: we DO ship Graphify's nudge ourselves precisely because its self-installer is too invasive to run.

**Why commit `.serena/memories/` but not `.serena/project.local.yml`:** the memories directory contains Serena's onboarding summaries of the codebase — they act as team-shared context (a teammate cloning the repo skips re-onboarding). The local YAML holds per-user overrides (LSP paths, language toggles) which are environment-specific.

**Why a `When to prefer Serena tools` block in CLAUDE.md:** community reports indicate Opus under-uses Serena's symbolic tools without an explicit prompt. The block is conditional — present only if Serena was selected during `/init-project` — so projects without Serena are not polluted with irrelevant guidance. Mirrored as a short note in `rules/ai-collaboration.md` so the agent picks it up when the rule loads on demand.

### 14. Database validation as an agent, not a skill — and not a hook

**Considered:** three shapes for "let Claude query the project's database":
- (a) A slash command `/db <query>` — a skill that executes a query and prints the result.
- (b) A read-only MCP server (like Postgres MCP Pro) as the only path.
- (c) A sub-agent that takes an expectation, plans its own queries, and returns a verdict.

**Chosen:** option (c) as the primary artifact (`db-inspector` agent), with the MCP as a complementary opt-in for Postgres-specific tooling.

**Scope (revised):** the agent was originally named `db-validator` and scoped to post-change validation only (return a `VERDICT`). Real usage showed a second need — reading a fact mid-task to inform a decision ("how many active users?", "does this row exist?") — so it was renamed `db-inspector` and given a second mode that returns the data plus the query (`ANSWER`). The agent reasoning (below) applies to both modes; only trivial one-line SELECTs stay in the main session, where a raw `psql` call is cheaper than spawning an agent. It also learned to run the client inside a Docker container (`docker compose exec -T`) when there is no host binary.

**Why an agent, not a skill:** the real-world use case is "I implemented feature X, verify the database is now in the expected state." That requires:
1. Reading the expectation in natural language.
2. Planning 1–3 queries (often introspect schema first, then query the data).
3. Synthesizing a verdict from raw rows.

A skill is a one-shot tool: it runs, returns, exits. The main session would have to orchestrate the plan, parse the output of each query, and accumulate raw tabular data in its context window — exactly the kind of noise sub-agents are designed to absorb. An agent runs in an isolated context, dumps the tables internally, and returns only "VERDICT: OK / FAIL / INCONCLUSIVE + minimum evidence." Same shape as `code-reviewer` and `debugger` already in the template.

**Why not only the MCP:** Postgres MCP Pro is excellent but (1) Postgres-only — SQLite users get nothing; (2) requires `uv` and a one-time `uv tool install` — a hard prerequisite; (3) does not solve the "synthesize a verdict from results" problem on its own. The agent works with just the CLI client (`psql` / `sqlite3`), which devs typically already have. The MCP and the agent then coexist with clear division of labor: agent = post-change verification, MCP = ad-hoc queries + performance analysis. Documented in the template README under "Relation to Postgres MCP Pro".

**Why read-only with no escape clause:** validation never needs to mutate. Mutations are the user's job in the main session, with explicit confirmation. Hard-enforcing read-only in the agent prompt (allowlist of `SELECT`/`EXPLAIN`/`WITH ... SELECT`/meta-commands, denylist of mutating substrings) gives the same guarantee that hooks provide for `rm -rf` / force-push: even if the model tries, the tool refuses. Not as deterministic as a hook (the LLM enforces it on itself), but the failure mode is much narrower than mutating production data by accident.

**Why the read-only enforcement lives in the agent prompt, not a hook:** a hook on `Bash(psql:*)` would have to parse arbitrary SQL — psql accepts queries on stdin, in files (`-f`), through env vars, and via heredocs. That parser is hard to write correctly and would be the same kind of attack surface that bit the archived `@modelcontextprotocol/server-postgres`. Keeping the validation in the agent prompt is "trust but verify" defense: not a hard sandbox, but a layered defense that's clearly worse to bypass than to follow. For genuinely sensitive data, the template README recommends using a DB role with no write privileges for `DATABASE_URL`, which IS deterministic.

**Why conditional deployment via `/init-project`:** the agent is only useful if the project has a SQL stack. Adding it everywhere would clutter projects that don't (a CLI tool, a static site, a Rust kernel module). `/init-project` detects Postgres or SQLite from dependencies and DB files; if neither is present, it removes the agent during the copy step. Same pattern as the OS-specific hook cleanup.

**Why not MySQL/MongoDB on day one:** scope. MySQL would be a straightforward addition (allowlist for `SHOW`/`DESCRIBE` meta-commands, swap `psql` for `mysql -e`). Mongo is fundamentally different (no SQL, the denylist substring approach doesn't apply, would need a JSON-schema-based filter for read-only `find`/`aggregate` operations). Both are deferred to the "Open questions" list — add them if real usage demands it.

### 15. `/init-project` plans, the user executes

**Considered:** three shapes for the deployer skill:
- (a) Skill runs `bash init.sh` directly via `!`-prefixed shell blocks. Single command from the user's perspective.
- (b) Skill writes every file via the `Write` tool, no shell involved.
- (c) Skill detects stack and prints the exact terminal command for the user to run, then resumes to fill placeholders after the user confirms.

**Chosen:** option (c).

**Why not (a):** sustained effort to make it work failed. The permission matcher rejects shell constructs the skill needs (compound commands #16561, `$HOME` against non-`bash` binaries #43713, exit-non-zero treated as fatal). Worse, Claude Code's progressive-disclosure mechanism reads `.claude/rules/*.md` into context while the skill runs, racing with the file copy and producing "cp: File exists" against files that were just `rm -rf`'d (#35096). Audit of public scaffolding skills (anthropics/skills, vercel-labs/skills, hmohamed01/Claude-Code-Scaffolding-Skill, bentsolheim/claude-skill-bash) confirms none of them attempt in-skill file deployment — they all delegate to external scripts.

**Why not (b):** the template is ~25 files. Writing each via `Edit`/`Write` is slow (>25 tool calls), noisy in the conversation, and duplicates logic that already lives in `init.sh` (hook OS filtering, db-inspector conditional removal, Serena MCP handling, .gitignore merging). It also makes standalone use (CI, scripted machine setup) awkward — there's no shell entry point.

**Why (c):** clean separation of concerns. The skill does what skills are good at (interviewing, reasoning about stack, computing the right flags); the script does what shell is good at (copying 25 files atomically without a Claude Code session interfering). The user copies one command between two windows — small friction, no race conditions. After the deploy, the skill resumes and uses `Edit` to fill placeholders in `CLAUDE.md` and `settings.json`, which is fast (few targeted edits) and safe (no race because the rule files aren't being modified, only the docs).

**Trade-off:** not a single-click experience. Accepted because the alternative is layered workarounds against runtime bugs we don't control. If Anthropic fixes #35096 and the matcher restrictions, we can revisit option (a).

### 16. Optional project description as a bias, not a branch

**Considered:** three shapes for letting the user describe the project before the technical interview:
- (a) Don't ask — keep the interview neutral and let the user steer through individual answers.
- (b) Ask, then use the description to pick a stack-specific path (Django flow, Next.js flow, mobile flow, …).
- (c) Ask optionally; if given, use the description to reorder and re-label options inside the existing neutral interview, marking the best fit `(Recommended)`. If declined, run the original neutral flow.

**Chosen:** option (c). Documented in `skills/init-project/SKILL.md` §0.

**Why not (a):** the neutral interview presents every framework on equal footing. For a user who already knows they want "a scraper that runs daily on a VPS," seeing "Frontend" and "Library" alongside "Script" as equal options is noise. Worse, without context the skill can't reason about cross-cutting choices — e.g. whether to recommend Docker Compose (yes if VPS self-hosted, no if Cloudflare Workers), or which MCPs are likely useful (Playwright for scraping/E2E, Serena for a large codebase). Cross-question coherence is hard without a project goal.

**Why not (b):** reintroduces the stack-variant problem that decision 2 already rejected. A "Django flow" and a "Next.js flow" diverge in skills, hooks, rules, agents — over time they drift, duplicate logic, and reopen the maintenance burden the neutral template was designed to avoid. Branching the flow also makes the skill harder to reason about: every code path has to be tested against every other.

**Why (c):** the interview structure is preserved (same questions, same answer sets, same SKILL.md sections §1–§9). The description only affects (1) the order of options inside each AskUserQuestion call and (2) the per-option `description` text that explains why this option fits or doesn't. The user can always pick a non-recommended option or "Other"; the bias is suggestion, not constraint. This keeps the neutral-template guarantee from decision 2 intact while removing dead-weight options for users who already have a clear goal.

**Why optional, not mandatory:** sometimes the user is exploring ("I don't know yet, just want to set up Claude Code"), or the project is genuinely ambiguous, or they prefer to think one question at a time. Forcing a project description would gate the skill behind a paragraph of writing the user may not be ready to produce. Defaulting to "No" preserves the original behavior exactly.

**Why skipped on re-runs:** the project's deployed `CLAUDE.md` already documents what the project is (`## WHAT — Stack`, `## WHAT — Deployment`, etc.). Asking again on every refresh would be redundant and could conflict with the existing documented intent — the source of truth on re-runs is the file on disk, not a fresh user-stated description.

**Trade-off:** Claude has to translate a free-text description into per-question biases on the fly. The mapping is fuzzy — "edge function" might mean Cloudflare Workers, Vercel Edge, Deno Deploy, or Lambda@Edge. The skill mitigates this by treating the description as soft context: if the user contradicts the bias later in the interview, the skill accepts the contradiction rather than insisting (documented in SKILL.md §0).

### 17. Portable `docs/` seeded for every project, maintained by `/update-docs`

**Considered:** three shapes for project-level documentation:
- (a) Don't ship any docs convention. Each project invents its own (or doesn't document).
- (b) Ship a single `docs/architecture.md` and let projects extend it.
- (c) Ship a `docs/` directory with `README.md` (the convention) plus a small set of contract files split by *lens*, and a `/update-docs` skill that keeps them in sync with the code.

**Chosen:** option (c). Implemented in `templates/project/docs/` (the seeds) and the `update-docs` skill (now central, in `global/.claude/skills/update-docs/` post-§23). The contract surface is split into three files by the question they answer (see "the three-lens split" below): `backend.md` (the API), `ui.md` (the visual contract), and `user-stories.md` (the behavioral contract).

**Why not (a):** the trigger was concrete and recurring. When working on a project with a Rust backend and an iOS client, the user switches editors (VSCode for backend, Xcode for iOS). Xcode only sees the iOS subdir — Claude inside Xcode has no view of the backend's endpoints, request/response shapes, or auth model. The user was producing ad-hoc context docs by hand every time. A portable `docs/` that travels with the repo solves this once for every cross-editor / sandboxed-tool situation.

**Why not (b):** "architecture" is a fuzzy bucket. The user does not want narrative — they want precise, separable contracts. Splitting by lens matches the actual seams a contributor reasons about.

**Why (c):** the docs describe the **public contract**, not the implementation. Implementation lives in source files; `docs/` is what survives a context boundary (Xcode, embedded subdir, fresh contributor). Coverage-over-depth is the binding rule — every endpoint, section, and capability must appear, even as a one-liner. A docs file that omits 30% of the surface is worse than no docs, because it builds a false sense of completeness.

**The three-lens split (`backend.md` / `ui.md` / `user-stories.md`):** the surface originally shipped as two files (`backend.md` + `frontend.md`, where `frontend.md` mixed sections, the endpoints each consumed, and design tokens). That conflated three different questions, so it was re-split by lens:
- `backend.md` — *what can a client call?* (API contract).
- `ui.md` — *what does it look like and what screens exist?* (brand design tokens + section map only; the old "which endpoints this section consumes" wiring was dropped — it duplicated `backend.md` and went stale).
- `user-stories.md` — *what can the user achieve?* (behavioral contract, platform-agnostic).
One feature appears in all three under a different lens, with no duplicated detail. The behavioral lens is the one a non-technical stakeholder and a cross-platform team actually share, and it was missing entirely before.

**The fourth file, `conventions.md` — the repo-versioned copy of the conventions.** The three above are *product* contracts (what the system does). `conventions.md` is a *process* contract (how to write the code): typing, error handling, security, git discipline, output style. It exists because the three product docs solved half the cross-editor problem and left the other half open: a tool that reads `docs/` but does not run Claude Code (Xcode, a sandboxed editor, a different assistant) learns *what to build* but never sees the rules, so it builds to no standard.

**Which of the two is canonical.** The first wording made `.claude/rules/` the single source of truth — repo-relative, which resolved nowhere in a clone, since the rules are installed at `~/.claude/rules/`. Correcting the path exposed the deeper problem: those rules are *per-developer global config*, so (a) no clone contains them, and (b) two contributors can legitimately hold different ones, which makes "the global rules win" ill-defined for anyone but their owner. So `conventions.md` is canonical: it travels with the repo, is present for every contributor and every non-Claude tool, and depends on no tool-specific config. Claude Code users additionally load the same conventions from `~/.claude/rules/`; when the two diverge, they are reconciled by hand rather than by precedence. Adopted from the wording `artemis` had already converged on independently. The unavoidable cost is a sync obligation between the two; mitigated by (1) `conventions.md` being a concise summary, not a paste, so it drifts slowly and visibly; (2) `update-docs` treating a `.claude/rules/` change as a trigger to re-sync; (3) `/compound` reminding to mirror any rule it lands in `.claude/rules/`; (4) the file's own footer stating the obligation for hand-editors; (5) the `sync-mirror-docs` PostToolUse hook (below). Accepted over the alternative of having Claude-only conventions, which silently fails for every non-Claude-Code tool.

**Why a `sync-mirror-docs` hook, when DESIGN.md is otherwise wary of advisory hooks.** Mitigations (2)-(4) all depend on remembering to run a skill; the sync obligation is exactly the kind of discipline §10 says should become a deterministic signal. So a PostToolUse hook fires the instant a `.claude/rules/*.md` file is edited and prints a one-line reminder to update `docs/conventions.md` (and the output style, for `ai-collaboration.md`). This does NOT contradict the rejection of a `Stop`-hook-for-`/compound` ("Things deliberately not included"): that one would fire on *every* turn end (high noise, low signal); this fires *only* on a rules edit (gated by `if: "Edit(.claude/rules/*)"`), which is rare and always relevant. It is **non-blocking** — editing a rule is legitimate and must never be gated; the hook surfaces the obligation, it does not stop the edit.

**Revised 2026-08-15 — the advisory channel was a dead end.** The hook (and the two `prefer-*` nudges, §13/§21) delivered its note on **stderr with exit 0**, which the hooks reference is explicit about: stderr from an exit-0 hook goes to the debug log only, and the model never sees it. All three hooks had therefore been inert since they shipped: the "deterministic signal" this section claims existed as a process that ran and printed into a void. They now emit `{"hookSpecificOutput": {"hookEventName": ..., "additionalContext": <note>}}` on stdout, still exit 0 — the documented channel for delivering context to the model **without** blocking, which is exactly what §21 wanted and could not express at the time. The `if:` gate was also dropped: it keyed off `Edit` only, so a `Write` to a rule file never fired it, and prefix-anchored `if` patterns were reopening bypasses elsewhere (§18). The hook self-gates on the path instead. Because `additionalContext` now genuinely enters the context on every firing, the two high-frequency nudges gained a 5-minute per-project debounce; `sync-mirror-docs` did not need one (rule edits are rare and each one really does carry the obligation).

**Platform model: parity by default.** `ui.md` and `user-stories.md` describe one product implemented by N clients (web/iOS/Android/desktop). They are written once, platform-agnostic; a divergence is recorded as an explicit exception line, not as a per-platform matrix on every entry. This keeps the common case (full parity) terse and makes the rare divergence visible.

**Self-contained maintenance (usable without the skill).** Each doc carries its own "how to keep it true" header in plain language. The point of `docs/` is to survive a context boundary — including one where Claude Code and `/update-docs` are not available (Xcode, a teammate editing by hand). So the maintenance rules live *in the file*, and `/update-docs` is the convenience path, not a dependency. This is why the headers restate coverage-over-depth and the contract-change criteria instead of only pointing at `docs/README.md`.

**Why `/update-docs` (skill + rule, not a hook):** option-A vs option-B was discussed in the session. A hook that fires on every edit would either (1) miss the contract changes that span multiple files or (2) cry wolf on every internal refactor. A skill that reads the diff and reasons about contract impact is more accurate. The cost is that Claude must remember to invoke it — addressed by hard-coding the rule in `CLAUDE.md.template`'s `## Portable docs — \`docs/\`` section, which is always loaded.

**Why design tokens belong in `docs/ui.md`, not a separate `docs/design-system.md`:** tokens are cross-client contract — same names and values across web, iOS, Android, desktop. They are the visual half of the same "what the user sees" surface that the section map describes, so they live in the same file. Splitting them out would create a sibling file with no reason to exist; the rule of "cover everything, don't proliferate files" wins.

**Trade-off:** the docs require discipline to stay true. `/update-docs` reduces the burden but does not eliminate it — a sloppy session that closes without invoking the skill leaves drift. The mitigation is the rule in `CLAUDE.md.template`: at task close, if any contract may have changed, the skill MUST run. Reality will determine whether ~85–95% adherence is enough; if not, we revisit a `PostToolUse` hook as a hardener (deferred until usage shows it's needed).

### 18. `guard-push-main` is opt-out via `settings.local.json`, not always-on

**Considered:** three shapes for handling the "I work entirely on main" workflow:
- (a) Keep the hook always-on. Solo projects work around it by deleting the hook or bypassing manually.
- (b) Ask in `/init-project` (branches vs main). If main, don't deploy the hook.
- (c) Ship the hook always, read `"allowPushToMain": true` from `.claude/settings.local.json` (gitignored) at runtime. Default: block. Force push stays blocked regardless of this flag.

**Chosen:** option (c). Implemented in `guard-push-main.{sh,ps1}` (now central, in `global/.claude/hooks/` post-§23) and asked at the end of `/init-project` (§7b in SKILL.md).

**Why not (a):** the hook saves users from accidental `git push origin main` on team projects (real). On solo/prototype repos that legitimately live on main, blocking every push is just friction. Forcing a workaround on every personal repo is a worse default than letting users opt out.

**Why not (b):** two reasons. First, splits the template's hook set into two variants — a maintenance burden whose first symptom is silent skew between project setups. Second, it removes the force-push protection from main-only workflows, which is wrong: force push rewrites shared history regardless of how anyone works locally. Force push is **always** dangerous; pushing to main is **sometimes** legitimate. The two need different treatment.

**Why (c):** preserves the single hook implementation; preserves force-push protection unconditionally; lets the opt-out live in a gitignored file (so a developer's personal "I'm OK pushing to main here" choice is never imposed on the rest of a team that later joins the repo). `/init-project` offers to set the flag at the end of the deploy as a convenience; the user can also flip it manually any time without re-running the skill.

**Trade-off:** users must know the flag exists to use it. Mitigated by (1) the hook's own block message naming the flag explicitly, (2) `settings.local.json.example` documenting it inline, (3) `CLAUDE.md.template`'s Workflow section mentioning it, (4) the `/init-project` interview asking proactively.

**Match on the push target, not on the string "main" (fixed 2026-07-26).** The first implementation grepped the command for `--force`/`-f` and for `main` as a trailing token. A probe of ten push forms found **seven passed**: `+main:main` and `+HEAD:refs/heads/main` (a leading `+` on a refspec forces the update exactly like `--force`, so the guarantee this section calls unconditional was open), `HEAD:main` / `main:main` / `refs/heads/main` (refspecs whose destination is main but whose string does not end in it), `git -C /repo push origin main`, and plainest of all, a bare `git push` while checked out on main — the single most common way to reach main, and invisible in the command string. The hook now parses the refspec destination, and when the command names none, resolves `git symbolic-ref --short HEAD`. All ten forms behave correctly, including under the opt-out (which permits main but still blocks the `+` refspec). The lesson generalizes: **a guard that matches surface syntax guards the syntax, not the operation.**

### 19. `init.sh --update`: three-class refresh + drift report + bullet reconciliation

> **Largely superseded by §23 (2026-05-30).** Centralization removed the
> per-project hooks/agents/skills/rules, so the three-class refresh below no
> longer applies — those update via `git pull && ./install.sh`. What survives:
> `init.sh --update` now only seeds missing per-project files and drift-reports
> `settings.local.json.example`, and the skill still does the CLAUDE.md bullet
> reconciliation (§1d). The reasoning below is kept as the record of the prior
> model; read §23 for the current one.

**Considered:** three shapes for picking up template improvements in already-initialized projects:
- (a) Re-run `/init-project` from scratch. Overwrite everything, lose user edits.
- (b) `--update` mode that only adds missing files (the original behavior up to the design tokens commit). Preserves user edits but never refreshes anything that exists.
- (c) `--update` mode with three file classes — always-refresh (hooks), refresh-if-untouched (rules, settings.local.json.example), add-if-missing (agents, skills) — plus DRIFT lines on stderr for any file the user edited that the template also updated, plus a CLAUDE.md bullet reconciliation step run by the skill.

**Chosen:** option (c). Implemented across `templates/project/init.sh` + `init.ps1` (the three-class policy and DRIFT emission) and `skills/init-project/references/update-mode.md` §1b/§1c/§1d/§1e (the parsing, the report, the bullet diff, and the Serena/Graphify improvement reconciliation for projects that opted into Serena before the template added those improvements).

**Why not (a):** loses user edits silently. The user is the source of truth for their CLAUDE.md, their docs/, their per-project settings.json — never overwrite.

**Why not (b):** misses the actual case the user hit. The session added quoted YAML descriptions to rules/, H1 headings to agents/, new bullets to CLAUDE.md.template, and a new `--update`-aware DRIFT mechanism — none of those reach an old project under "add missing only," because the files already exist. Old projects stay stale forever.

**Why (c):** matches the user's mental model of "authority" per file class. Hooks are security-relevant and the template owns them — always refresh. Rules are mostly descriptive, but the user might have added a project-specific paragraph — so refresh only if untouched, otherwise flag drift. Agents and skills are the most likely to be customized — keep them, flag drift. settings.json carries placeholders the user filled in (`{{SCRIPT_EXT}}`, MCP wildcards) — never auto-refresh; flag drift only. CLAUDE.md.template's new bullets are offered via `AskUserQuestion` multiSelect so the user picks individually — granular, non-destructive.

**Why DRIFT on stderr (not stdout, not a separate file):** the skill captures stderr, parses the prefixed lines, and shows the user a clean report. Putting DRIFT on stdout would mix it with the `deploy OK` confirmation; using a sidecar file would require IO ordering guarantees the script doesn't make.

**Why a lenient match for the bullet diff (8-word prefix + prefix-of):** false negatives (offering a bullet the user already has, lightly reworded) are mildly annoying — the user can deselect. False positives (silently skipping a genuinely new bullet because of a wording overlap) defeat the purpose. The match leans toward over-offering, with the AskUserQuestion as the final filter.

**Trade-off:** the policy is now more nuanced and harder to explain to a casual user. Mitigated by inline header comments in `init.sh` / `init.ps1`, by the SKILL.md §1b walkthrough, and by the fact that the default `--update` invocation does the right thing without the user needing to know the classes.

### 20. Not packaged as a Claude Code plugin / marketplace

**Considered:** distributing the template as a Claude Code plugin published to a marketplace (`plugin.json` + `marketplace.json`, `claude plugin install`, `defaultEnabled`), instead of `install.sh` copying files plus the `/init-project` planner skill.

**Chosen:** keep `install.sh` + `init.sh` + the planner skill. Do NOT package the whole thing as a plugin.

**Why three blockers survive any plugin packaging:**
1. **No `rules` component.** The `plugin.json` schema ships skills, commands, agents, hooks, mcpServers, outputStyles, lspServers, experimental, userConfig, channels, dependencies — but there is no component for `.claude/rules/*.md`. The whole progressive-disclosure design (decision 3) depends on shipping those four rule files; a plugin can't.
2. **No per-project CLAUDE.md.** A plugin's root CLAUDE.md is not loaded as project context. There is no plugin equivalent of the `CLAUDE.md.template` + `{{placeholder}}` flow (decision 15), which is the core of what `/init-project` personalizes.
3. **Not committed per project.** Marketplace plugins live in `~/.claude/plugins/cache` and are used in place. That breaks the founding model (decision 1): config follows the project, is committed, and the team inherits it via `git clone`.

**Nuance:** a plugin *can* ship a skill that runs a script, so a plugin could in principle host an `/init-project`-style deployer. But blockers (2) and (3) survive that workaround — the deployed artifacts still have to be real files in the project's `.claude/`, not plugin-cache content.

**Viable hybrid (left as an open question):** publish the genuinely stack-neutral skills and agents as an *optional* plugin for users who want them globally, while keeping rules + CLAUDE.md + hooks in `init.sh`. Not pursued now — it doubles the maintenance surface for marginal gain.

**Source:** Claude Code plugins-reference and plugin-marketplaces docs; `defaultEnabled` added in changelog 2.1.154.

### 21. OS-level sandbox is a documented non-goal, not a shipped default

**Considered:** shipping `sandbox` settings (`sandbox.filesystem.denyRead`, `network.deniedDomains`, etc.) so the template enforces filesystem/network boundaries at the OS level, given the security focus.

**Chosen:** do NOT ship sandbox config. Document it as a reasoned non-goal here (and optionally point power users at it from `rules/security.md`).

**Why the sandbox is genuinely stronger than the deny rules:** Read/Edit deny rules apply to Claude's built-in file tools and to file commands it recognizes in Bash, but **not** to arbitrary subprocesses (a Python or Node script that opens `.env` itself slips past them). The OS-level sandbox blocks all processes. So it is not redundant with decision 9 — it is a strictly stronger layer.

**Why not ship it by default anyway:**
- **Host prerequisite the template can't guarantee.** On Linux/WSL2 it needs bubblewrap + socat installed; same class of problem as Serena's `uv tool install` (decision 13), which is why Serena is opt-in.
- **No native Windows support.** Half the template's audience can't use it.
- **Conflicts with what this template scaffolds.** The `--compose` / `--runtime` flags scaffold Docker workflows; Docker is incompatible with the sandbox and would have to be listed in `excludedCommands`. Shipping a sandbox that breaks the template's own Docker path is a bad default.

**Conclusion:** the deny rules + guard hooks are the right always-on default; the sandbox is an opt-in hardening for users on a supported host who want defense against prompt-injected subprocess reads. Same opt-in logic as Serena. **Source:** permissions and sandboxing docs; `autoAllowBashIfSandboxed` (changelog 2.1.139).

### 22. Tone/language conventions: rule by default, output style as opt-in hardening

**Considered:** the "Castilian conversation / English code / no emojis / cite sources" conventions could live (a) only as advisory prose in `rules/ai-collaboration.md`, (b) only as an output style, or (c) both — prose as the always-on baseline plus an output style for stronger enforcement.

**Chosen:** option (c). The prose stays in `rules/ai-collaboration.md` as the always-on fallback; the same conventions ship as `.claude/output-styles/dotclaude.md` (`keep-coding-instructions: true`), enabled per-machine via `/config` or `"outputStyle": "dotclaude"`.

**Why not output-style-only:** an output style is selected via `/config` and saved to `settings.local.json` (not versioned by default). A teammate who clones the repo and hasn't enabled it would lose the conventions entirely. The always-on rule guarantees a baseline for everyone.

**Why offer the output style at all:** it modifies the system prompt, so it applies inside sub-agents and skills too — stronger and more consistent than an advisory rule the model may under-follow. Same opt-in shape as Serena (decision 13): the template ships it, the user activates it. `init.sh`/`init.ps1` copy `output-styles/` like any other `.claude/` subdir (full copy on first deploy; add-if-missing + drift-report on `--update`, Class B). **Source:** output-styles docs.

**Trailer note (decision 9 / §10 cross-ref):** the `Co-Authored-By` trailer is now disabled deterministically by `attribution` in `settings.json`, so `rules/workflow.md` only carries a one-line pointer plus the "don't add it by hand" reminder — the mechanical guarantee moved out of prose, exactly the §10 principle. `attribution` controls Claude Code's automatic byline, not a hand-written trailer; a `Bash(git commit *)` PreToolUse guard remains an open question if that ever proves necessary.

### 23. Centralized core + per-project surface (supersedes the all-per-project model)

**Considered:** the original model copied the entire `.claude/` (hooks, agents, skills, rules, output-styles + CLAUDE.md/docs/settings) into each project (decision 1). The pain that surfaced in real use: improving the master repo did nothing for existing projects — each had to be updated one by one with `init.sh --update`, and there was no way to know which projects were stale. That does not scale.

**Considered three fixes:** (A) a propagator that re-runs `init.sh --update` across all projects (still N operations, needs a project registry); (B) symlinks from each project into `~/.claude/` (breaks git — the symlink points at an absolute home path a teammate can't resolve — and is fragile on Windows); (C) split the surface: centralize the reusable artifacts in `~/.claude/` (the harness already loads user-scope config for every project) and deploy only the project-specific surface per project.

**Chosen:** option (C). The five reusable types — hooks, agents, skills, rules, output-styles — live in `global/.claude/`, are installed once into `~/.claude/` by `install.sh`, and apply to every project automatically. A master-repo improvement reaches all projects with `git pull && ./install.sh` — nothing to propagate. `/init-project` deploys only CLAUDE.md, docs/, a `settings.json` stub, and scaffolds — the genuinely per-project surface.

**Why this is safe given the harness's merge rules (verified against docs):** user-scope `~/.claude/` applies to all projects for every artifact type. Hooks and permissions **merge** across scopes (a project can only *add*, never remove a central hook). Skills resolve **user-over-project** (a project cannot shadow a central skill by name). Rules **merge** (`paths:` honored at user scope). So "central is immutable, project can only add" is deterministic for hooks, permissions, skills, and rules. For **agents** and `settings.json`, project *overrides* user natively — there the immutability is by **convention** (init does not deploy an editable copy, so there is nothing to shadow); a hard lock would need managed-settings (`strictPluginOnlyCustomization`), which is MDM-only and out of scope for a personal setup.

**Override model:** a project extends the central config by **adding** files in its own `.claude/` (a project-only rule, an extra agent) — never by editing the central ones. Central is read-only, enforced two ways: (1) the harness's precedence where it gives it (user-scope skills win over project, hooks/rules merge); (2) the **`guard-central-config` hook** — a central PreToolUse(Edit|Write) guard that blocks any edit whose resolved path lands under `~/.claude/{agents,rules,skills,hooks,output-styles}`. So even a stray "let me just tweak the global rule" from inside a project is refused (exit 2); the only way to change a central artifact is to edit its source in the dotclaude repo (`global/.claude/...`) and re-run `./install.sh`. The guard resolves `~`, relative paths, and `../` to a canonical absolute path before matching, so traversal can't dodge it; it deliberately does NOT match the repo source path, so maintaining dotclaude itself is unaffected. This makes the "read-only central" guarantee deterministic without managed-settings (which would be MDM-only).

**The accepted cost — this supersedes decision 1 for those five types.** The project's `.claude/` is no longer a self-contained package a teammate inherits purely by `git clone`; the central artifacts require having the master repo installed (`./install.sh`). Decision 1's "config follows the project, committed, team-inherited" still holds for what stays per-project (CLAUDE.md, docs/, the settings stub — all committed). The trade is acceptable here because the user works **solo** (D1): no team clones these projects, so the team-inheritance value of §1 was not being used for the five centralized types. For a team setting, this would need each member to run `./install.sh`, documented as a migration note.

**Knock-on simplifications:** `{{SCRIPT_EXT}}` disappears (no per-project hooks to template — `install.sh`/`install.ps1` resolve the OS form once when writing `~/.claude/settings.json`). The `--update` three-class drift policy (decision 19) collapses to seed-if-absent for the per-project files; hook/agent/skill/rule drift is gone because they are no longer copied. `db-inspector` is now always-central (no longer conditionally dropped by `--db`). `~/.claude/settings.json` is no longer minimal (revises decision 11): it now carries the base permissions + hooks, merged non-destructively so the user's personal keys survive.

**Source:** docs/settings (user vs project precedence, permission merge), docs/skills (user-over-project name resolution), docs/memory (user-level rules merge). Verified in this session.

### 24. `reinject-rules`: re-prime non-negotiable conventions after compaction

**Problem:** CLAUDE.md and `rules/` are re-read by the harness after a context compaction, but *adherence* to advisory prose decays when the transcript is summarized — the summary may drop the fact that a rule was being actively applied. This is the same failure mode that motivated the Serena drift-prevention hooks (§13): prose alone does not survive compaction; deterministic signals do (§10).

**Chosen:** a central `SessionStart` hook gated by `matcher: "compact"` (fires only on auto/manual compaction, never on normal session starts) that prints a short digest of the conventions whose only enforcement is prose: no `--amend`, no AI trailers, branch-per-feature, verify + CHANGELOG before done, AskUserQuestion for decisions, Serena/Graphify preference, challenge assumptions. Stdout from a SessionStart hook is added to the fresh context (verified against docs/hooks). Deterministic guarantees (guard-destructive, guard-push-main, detect-secrets, guard-central-config) are deliberately NOT restated — they fire regardless of what the model remembers.

**Accepted cost:** the digest is a second copy of prose that lives in `rules/workflow.md` and `rules/ai-collaboration.md`, so it carries a sync obligation. Mitigated the same way as `conventions.md` (§17): the `sync-mirror-docs` hook's reminder now also names `reinject-rules.{sh,ps1}` when a rule file is edited, and the hook's own header states the obligation. Kept as a hardcoded digest rather than generated from `rules/` because the value is *selection and brevity* (a ~8-line distillation), not completeness — generating it would re-inject the full rules that the harness already re-reads.

### 25. `check.py`: a coherence validator, because prose does not enforce lockstep

**Problem (found by auditing, 2026-07-26).** The repo carries ~28 hand-maintained duplications — 17 `.sh`/`.ps1` pairs, permission rules mirrored into `install.ps1`, extension globs repeated across two rules and two hooks, artifact inventories restated in three docs. Their only enforcement was prose (`CLAUDE.md`: "when you change one, change the other in the same commit"). An audit found **four of the five spot-checked duplications had already diverged**, including Windows silently losing the `sudo`/`dd`/`mkfs`/`shred`/`truncate` denies. This contradicts §10 on its own terms: §10 says a non-negotiable guarantee belongs in a deterministic check rather than in prose, and lockstep parity was being treated as non-negotiable while enforced only by prose.

**Chosen:** `check.py` at the repo root, run by the maintainer (`python3 check.py`). Nine checks, each encoding a duplication the architecture genuinely requires: hook `.sh`/`.ps1` pairs, installer/deployer pairs, every hook wired in `settings.json` existing on disk, `install.ps1` deriving its rules from the JSON, doc inventories matching the artifacts, the shared extension lists agreeing, no inline interpreters in skills (§5), DESIGN.md's structural headings surviving, and every shipped JSON parsing.

**Not CI.** "CI/CD templates" is rejected below, but that rejection is about *what projects deploy* — a GitHub Action is project infrastructure. This is internal validation of this repo, the same category as the manual `python3 -m json.tool` step `install.sh` already runs. It stays a script the maintainer invokes, with no new dependency and no hosted runner.

**The validator earns its keep immediately:** on first run it found that `code-quality.md` and `security.md` excluded `.sql`, `.vue`, `.svelte`, `.pyi` and five other extensions that the Serena hooks already treated as code — so editing a SQL migration or a Vue component loaded *no* quality or security rule at all. It also caught a bug in itself: the inline-interpreter check used `glob("**/*.md")`, which skips dot-directories, so it was blind to every central skill under `global/.claude/skills/`. Both were invisible to reading and obvious to running — which is the whole argument for the file existing.

**The validator is itself tested** (`tests/check-selftest.sh`): it injects each regression `check.py` claims to catch and asserts a failure, with a control run on a pristine copy. That is what surfaced the dot-directory blind spot above — without it, `check.py` reported PASS on a repo containing the exact bug it was written to catch, which is strictly worse than having no validator, because it converts an unknown risk into false confidence. Any new check gets a self-test case; a check that cannot fail is not a check.

**Companion:** `tests/guard-push-main-cases.py` is the behavioural contract for the hook §18 covers — 61 cases as of the §27 audit, runnable against both the `.sh` and the `.ps1` (`--pwsh`) so lockstep is *verified* rather than asserted. `check.py` in turn asserts that the known-bypass cases stay in that matrix, since a deleted case is invisible in a passing run.

### 26. Calibrating the two noisy hooks: a warning that cries wolf protects nothing

**Problem.** `detect-secrets` and `guard-destructive` both matched surface text, and both were miscalibrated in *opposite* directions at once. Measured, not theorised — every case below was reproduced against the shipped hooks:

| Hook | Fired when it should not | Silent when it should not be |
|---|---|---|
| `detect-secrets` | `.env.example` (the file `/init-project --fullstack` ships and `.gitignore.template` whitelists), `credentials-policy.md`, and the hook's own source (its path contains `secrets`) | `API_KEY=sk-live-…` in a `.env` — the pattern was case-**sensitive** and required quotes, so the universal spelling was invisible |
| `guard-destructive` | writing docs or a commit message that merely *mentions* `rm -rf` or an inline interpreter, via heredoc | — (the first *fix* introduced six, see below) |

**Why the false positives are a security problem, not a nuisance.** A hook that fires on files which by definition hold no secret trains the model to treat its output as noise — and the next warning, the real one, gets the same treatment. Worse, `guard-destructive` only sees `Bash`: blocking a heredoc that documents dangerous shell pushes the model toward `Write`/`Edit`, which this hook never inspects. The false positive actively teaches the wrong escape route. §10 says a deterministic guard beats prose; that only holds while the guard stays credible.

**Chosen — `detect-secrets`.** Exempt from the *path* rule: placeholders (`*.example`, `*.sample`, `*.template`, `*.dist`, plus infix forms), markup prose (`.md`/`.mdx`/`.rst`), and this repo's own `hooks/` sources. Their **content** is still scanned, so a real key pasted into `.env.example` is still caught. Deliberately *not* exempt, each for a measured reason: `.txt` (the classic place to paste a key, and unlike `.md` it carries no structure suggesting documentation), the `.claude/` tree generally (`settings.local.json` holds tokens — only `.claude/hooks/` is exempt), and anything under `secrets/` or `credentials/` whatever its extension. The content pattern is case-insensitive, quote-optional, matches the JSON shape (`"token": "…"`, where the quote precedes the colon), and drops lines that *read* a secret from the environment — `token: process.env.X` is a reference, not a literal, and flagging it would re-create the cry-wolf problem on the content side.

**Chosen — `guard-destructive`: an allowlist, after the denylist form failed.** The first attempt stripped every heredoc body *unless* the opening line looked like an interpreter. That is unsound, because "does this line execute its body?" has no reliable negative: `docker exec -i c bash <<EOF`, `kubectl exec pod -- bash <<EOF`, `ssh host <<EOF` (SSH runs the remote login shell), `eval "$(cat <<EOF …)"`, and an *unterminated* heredoc (whose body-drop loop ran off the end of the command) were all silently stripped — six ways to execute `rm -rf /` unguarded. The shipped form inverts the burden: a body is dropped only on positive evidence of a file write — the line must be exactly a `cat >`/`tee` redirect to a filename, with no pipe, command substitution, chaining, or interpreter anywhere on it — and an unterminated heredoc keeps every line. **Unknown shapes fail closed.**

**The general lesson.** Both hooks' original bugs and the failed first fix share one shape: deciding a security question from surface text needs its *default* to be the safe answer. Matching "is this dangerous?" and exempting what looks safe puts the burden on enumerating every dangerous form — and the enumeration is always incomplete.

**Every change here is a loosening, so each hook got a case matrix** (`tests/{detect-secrets,guard-destructive}-cases.py`), runnable against both the `.sh` and the `.ps1`. They earned it immediately and repeatedly: the first `detect-secrets` exemption was too broad (`*.txt` exempted `secrets/prod.txt`); the `.sh` used a case-sensitive `case` while PowerShell's `-match` is case-insensitive by default, so the two disagreed on `SECRETS/` until the shell side lower-cased the path; and the six heredoc bypasses above are now pinned cases. None of those were visible to a careful read. `check.py` asserts that each of the three safety hooks keeps its matrix, since a deleted matrix is invisible in a passing run.

### 27. What a 26-agent audit of this repo found (2026-08-15)

Every file of the config was reviewed by its own agent, cross-checking against the official docs. The findings clustered into four failure modes worth naming, because each one is a *class* that will recur:

**(a) A mechanism that never ran.** The three advisory hooks (`prefer-serena-bash`, `prefer-graphify`, `sync-mirror-docs`) wrote to stderr and exited 0 — a channel the model never sees. They had been inert since they shipped, while §13/§17/§21 and `rules/ai-collaboration.md` all described the determinism they supposedly provided. **Lesson: a hook that emits advice needs its delivery verified once, by observing the model receive it — "the script runs and prints" is not evidence.** Fixed via `additionalContext` (§17).

**(b) A gate that reopened the bypass it sat in front of.** `guard-push-main` was wired with `"if": "Bash(git push *)"`. `if` patterns are *prefix-anchored*, so `git -C /repo push origin main` — an explicit BLOCK case in the matrix, and the exact wrapped form the hook's parser exists to catch — never reached the hook. The matrix passed the whole time because it invokes the hook directly, bypassing the gate. **Lesson: a hook's test must exercise the same path production uses, gate included; and a prefix pattern in front of a parser that handles non-prefix forms is a contradiction.** All `if` gates are gone from `settings.json`; every hook self-gates.

**(c) A guard whose comparison semantics did not match the filesystem's.** `guard-central-config` used case-sensitive `StartsWith` on Windows and a case-sensitive `case` on macOS — both case-**insensitive** filesystems, so `~/.Claude/hooks/…` or a lower-case drive letter wrote the guarded file and passed. **Lesson: path comparisons must fold case wherever the filesystem does, and it is worth stating platform semantics as explicit per-runner expectations in the matrix (the new `guard-central-config-cases.py` does).**

**(d) Prose that outlived its referent.** After centralization (§23), several artifacts still pointed at `.claude/rules/`, `~/.claude/templates/`, or a project `settings.json` — `/compound` step 6 even instructed the model to do something `guard-central-config` blocks. `check.py` cannot catch this class (the paths are plausible strings), so it survives until something reads them carefully. **Lesson: a structural change needs a grep for the old path across skills, agents and prose in the same commit — not just in the code that resolves it.**

Two more findings were behavioural rather than structural and are recorded where they belong: `model: sonnet` pinned on `code-reviewer`/`debugger` against the documented `inherit` policy (§7), and `model: haiku` on `/verify` without `context: fork`, which downgraded the **rest of the caller's turn** — including the fix step the skill itself instructs. The general shape: *a per-component setting that leaks into its caller is worse than no setting*, and `context: fork` is what scopes it.

### 28. `/audit` — reviewing the code at rest, with the depth as a user choice

**Problem.** Every review path in the setup keys off *change*: `/code-review` and the `code-reviewer` agent on the diff, `/security-review` on the branch, `verify-on-edit` per file. Nothing looked at code already in the repo, which is exactly where vulnerabilities age, dead code accumulates and duplication settles.

**Chosen.** A central skill covering four dimensions (security, dead code, duplication/improvements, plus duplicated styles and component-worthy repeated markup on web projects), opening with a single `AskUserQuestion` for **depth** (light / per-dimension subagents / per-module fan-out with adversarial verification) and **scope**. Making depth an explicit question — rather than inferring it — is the point: the same request means "quick hygiene check" and "pre-release audit" depending on the week, and the cost difference between them is an order of magnitude.

**The deterministic detectors run at every depth** (knip, ts-prune, depcheck, vulture, deptry, jscpd, `cargo udeps`, the ecosystem audit commands, gitleaks). An import-resolving linter beats an LLM reasoning about reachability and costs almost nothing; depth scales only the agentic half, which supplies what tools cannot — semantic duplication, "this should be a component", logic-level authorization gaps. Two guards are written into the skill: it must report what it could **not** run (a silently half-run audit reads as a clean bill of health), and it must treat every dead-code hit as a candidate, since dynamic imports, reflection, framework entry points and config-referenced code are a well-known false-positive class. Fixing is a separate confirmation, because an audit reaches code the user never asked to touch.

**Revised 2026-08-15 — two rounds of questions, and `/security-review` folded in.** First use showed the skill firing all four dimensions at once, which is both the expensive shape and the unreadable one: a report mixing secrets, dead exports and CSS duplication gets skimmed, not acted on. So the questions now come in two rounds — **categories first** (`multiSelect`: security, dead code, duplication, comments/docs, tests, styles/components), then depth and scope — and nothing runs before both are answered. Only the selected categories get detectors and agents, which also makes the agent count a direct function of the answer ("~1 per category") rather than a fixed cost.

That change made `/security-review` redundant: it was "the security dimension over the working tree", which is now one category plus one scope. Keeping both would have meant maintaining the same checklist twice — and they had already drifted, since the audit's §27 pass fixed the untracked-file blind spot in one and not the other. It was deleted and its two unique assets (the twelve-point checklist and the new-dependency audit step) moved into the Security category. `/code-review` stays separate on purpose: it is a fast bug-focused pass over the diff, not a category-selectable audit, and the two answer different questions.

### 29. The second half of the audit: the deploy path (2026-08-15)

The §27 round covered the config artifacts. The remaining ten units — the two installers, the two per-project deployers, the templates, `init-project`, and the validator itself — turned out to hold the more damaging bugs, because they run *outside* Claude Code, where no hook or matrix was watching. Three were destructive:

**The installer deleted the user's own work.** `install.sh`/`install.ps1` removed each shared directory (`hooks`, `agents`, `skills`, `rules`, `output-styles`) before copying. Those directories belong to the *user* as much as to this repo: any skill, agent or rule they wrote themselves vanished on every `git pull && ./install.sh`. Fixed with a manifest of repo-owned files (`~/.claude/.dotclaude-manifest`), so the installer removes only what it shipped last time. **Lesson: "this directory is ours" is false whenever the directory is also an extension point — own files, not directories.**

**The `.gitignore` merge inverted negations.** Both deployers merged with `sort -u`. Order is semantic in `.gitignore` (`!x` only re-includes *after* the pattern that excluded it) and `!` sorts before everything, so negations were hoisted above their parents. Verified against real git under `LC_ALL=C`: the template's own `!.env.example` — a file `/init-project --fullstack` writes — ended up ignored, along with any negation the user had. **Lesson: never sort a file whose semantics depend on line order; append the missing lines instead.**

**Documented exit codes were unreachable.** `init.ps1` sets `$ErrorActionPreference = "Stop"`, under which `Write-Error` is a *terminating* error — so the script died with exit 1 and the `exit 3` / `exit 4` after it never ran, while `/init-project` keys its remediation off exactly those codes. Same root cause as the §27a stderr finding: a PowerShell construct that behaves differently from its Bash-shaped intent. **Lesson: on the `.ps1` side, assert the exit code, not just the message.**

Three more were silent-failure bugs of the §27 classes, found in new places: a `## graphify` marker in `detect-drift.py` that the template never emits (so the gap re-offered itself forever), the whole Serena/Graphify guidance sealed inside an HTML comment (stripped before CLAUDE.md reaches the model — invisible in *every* deploy), and `Bash(mkfs.*:*)` still vanishing on Windows because the two verb extractors disagreed by one character even after 9b24223 supposedly aligned them.

**The validator's own blind spots.** `check.py` derived its inventories *from disk*, so deleting an agent or an entire skill directory just shrank the glob and passed green — it verified that docs match reality, never that reality is complete. It also never looked at frontmatter, so a broken `---` fence or a `model:` pin on a reasoning agent (the §27 drift) sailed through. Both are now checks with self-test cases, bringing it to 14 checks and 16 self-tests. **Lesson: a check derived from the artifact it validates can only catch documentation drift, never loss.**

### 30. `.mcp.json` is composed, not copied (2026-08-15)

Adding `--xcode` exposed a latent flaw in how `--serena` deployed `.mcp.json`. Serena copied `.mcp.json.template` wholesale and guarded it with a whole-file `cmp`, aborting (exit 3) on any difference. That is fine for exactly one flag owning the whole file, and wrong the moment a second one exists:

```
init.sh --xcode && init.sh --update --serena          -> exit 3
init.sh --serena && init.sh --xcode                   -> ok, then EVERY later
                                                         --update --serena -> exit 3
```

The second shape is the dangerous one: the project ends up correct and only the *next* re-deploy fails — and that re-deploy is precisely the path `update-mode.md` §1e uses to reconcile drift. Worse, on a project with any hand-added server (a `playwright` entry, say), the `cp` silently discarded it.

**Chosen:** one fragment per server under `templates/project/mcp/`, and a single `merge_mcp_servers` / `Merge-McpServers` helper that inserts or updates by server key. Each flag owns only its own keys. This makes the flags order-independent, re-runs idempotent, and third-party servers safe — none of which the copy model could offer.

Two consequences worth stating:

- **Exit 3 is retired, not reused.** There is no whole-file conflict left to abort on. The number stays burned because a project running an older `init.sh` still emits it, and silently repurposing it would make `/init-project`'s remediation advice wrong.
- **§1e lost its only manual edit.** It used to `Read` + `Edit` `.mcp.json` by hand *because* `init.sh` could not self-heal a drifted file. Merging can: re-running `--serena` rewrites a stale `graphify.command: "python"` to the current `uv` form while preserving everything else. Removing a special case is the real win here; the flag combination was just what surfaced it.

**Lesson: a "copy the template" deploy step is a single-owner assumption.** It holds until the second opt-in arrives, then fails in the combination rather than in either flag alone — which is why `tests/mcp-merge-cases.py` tests *sequences* of invocations, not single runs. Four of its eleven cases failed against the pre-refactor code, including one nobody had predicted (a third-party server being dropped).

### 31. UI implementation: central skill + per-project browser MCP (2026-08-15)

The recurring failure in design-to-code work was handing the model a whole HTML mockup and asking for a replica: values get invented, sections bleed together, and nothing is verified until the end. The research consensus (Anthropic's "give Claude a way to verify its work", every serious community pipeline) converges on two mechanisms: extract structure *before* code (tokens, component tree), and close a visual loop (screenshot vs reference) *during* implementation.

**Chosen split:**

- **`implement-ui` is a CENTRAL skill** (`global/.claude/skills/`), because the pipeline — tokens into `docs/ui.md`, confirmed component tree, section-by-section with a verification gate — is stack-neutral and degrades gracefully: without a browser MCP it falls back to asking the user for screenshots. Every project benefits; nothing project-specific in it.
- **The Playwright MCP is PER-PROJECT** (`mcp/playwright.json`, deployed by `--ui`), same reasoning as Serena's §13: it has a host prerequisite (`npx`, plus a browser download on first use) the template cannot guarantee, and an MCP server in `.mcp.json` costs session context in every project that carries it — so projects without a web UI should not pay for it. Exit 7 mirrors the exit-4 shape (required binary missing).
- **Tokens live in `docs/ui.md`, not a new `design.md`** — the portable-docs contract (§17) already reserves exactly that section, and a second token file would split the source of truth.
- `--ui` OWNS the `playwright` key in `.mcp.json`: a hand-added entry is adopted (updated), not duplicated — pinned in `tests/mcp-merge-cases.py`.

**Rejected:** user-scope installation (`claude mcp add --scope user`) as the default recommendation. It works, but leaves nothing versioned in the project, so a second machine or collaborator silently loses the browser loop the skill's verification gate depends on.

## Things deliberately not included

- **Pre-baked stack variants.** See decision 2.
- **A `Stop` hook prompting for `/compound` at end of session.** Intrusive; the skill is enough.
- **CI/CD templates** (GitHub Actions, etc.). Project responsibility, not `.claude/` responsibility.
- **Pre-commit git hooks** (different from Claude Code hooks). Project responsibility.
- **Agent teams.** Experimental, not stable enough.
- **Stack-specific skills** (deploy-vercel, etc.). Added per project, not in the global template.
- **Plugin/marketplace packaging of the whole template.** No `rules` plugin component, no per-project CLAUDE.md, not committed per project. See decision 20.
- **OS-level sandbox config by default.** Stronger than deny rules but needs a host prerequisite, has no native Windows support, and conflicts with the Docker workflows this template scaffolds. Opt-in hardening, not a default. See decision 21.

## Open questions for future iteration

These came up in design but were intentionally left for after real-world use:

- Whether the model override policy (Haiku for mechanical) is too aggressive or too conservative — needs usage data.
- Whether `detect-secrets.sh` false-positive rate is tolerable or needs tuning.
- Whether the `Stop` hook for compound prompts should be added later if `/compound` is forgotten in practice.
- Whether the template should grow stack-specific overlay directories once enough patterns repeat.
- Whether `db-inspector` should grow MySQL support (easy, similar shape to Postgres) and Mongo support (different — needs a JSON-schema filter, not a SQL substring denylist). Defer until real usage demands it.
- Whether to publish the stack-neutral skills/agents as an *optional* plugin (decision 20's hybrid) for users who want them globally, while keeping rules + CLAUDE.md + hooks in `init.sh`. Doubles maintenance surface; defer until there's demand.

## What evolves and how

The template is a starting point, not a finished product. The intended workflow:

1. Deploy in a project with `/init-project`.
2. Use it. When a correction is systematic, dispatch `/compound`.
3. If the learning is local to that project, codify it in the project's `.claude/`.
4. If the learning is general (applies to all future projects), apply it to the SOURCE in this repo and commit it: a reusable artifact (hook, agent, skill, rule, output-style) goes to `global/.claude/`, a per-project seed to `templates/project/`. Never edit `~/.claude/…` — `guard-central-config` blocks it and `install.sh` overwrites it on the next run. Then `git pull && ./install.sh` on each machine.
5. On other machines: `git pull && ./install.sh`.

This is the compounding loop. Each correction strengthens the template, which strengthens every future project.
