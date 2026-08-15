# Reference: update mode (re-run path)

Loaded by `SKILL.md` step 1 only when `.claude/` already exists. Covers the
Refresh / Reconfigure / Full-re-init choice, the drift report, and the
CLAUDE.md bullet reconciliation. If this is a first-time deploy, you never read
this file.

## 1b. Update mode (re-run path)

If step 1 found that `.claude/` already exists, the project has been initialized before. The user is either refreshing the template (picking up new hooks/agents/rules added upstream) or reconfiguring after a change (e.g. added a database, decided to deploy to a server). Either way, do NOT run the full first-time interview again — that would re-ask every question and risk overwriting personalized files.

**What to read first** (regular `Bash` tool + `Read`):

- `CLAUDE.md` — extract the existing `## WHAT — Stack`, `## WHAT — Commands`, `## WHAT — Versions`, `## WHAT — Deployment`, `## WHAT — External integrations (MCP)`, `## WHAT — Structure` sections. These are your defaults.
- `.claude/settings.json` — extract `permissions.allow` to know which MCPs and DB tools are already authorized.
- `.mcp.json` (if present) — confirms which MCPs are wired up.
- `docker-compose.yml` / `Dockerfile` — re-detect Docker presence and service versions.

**Ask via AskUserQuestion**:

- "Found an existing `.claude/`. What do you want to do?"
  - **Refresh template only** — pull new files added to the template since the last deploy. Don't change CLAUDE.md or settings. Recommended for "just updating to the latest dotclaude."
  - **Reconfigure** — re-run a slimmed interview that uses the existing CLAUDE.md as defaults. Useful if the stack changed (added a DB, added Docker, changed deployment target).
  - **Full re-init from scratch** — start over. WARNING: this deletes `.claude/` first and re-runs the full first-time interview. Use only if the project drifted so far that starting fresh is cleaner than reconciling.
  - **Cancel** — exit the skill without changes.

### Path A: Refresh template only

**Most "I want the latest dotclaude" cases are no longer a per-project step.**
The hooks, agents, skills, rules, and output-styles are CENTRAL — to get the
newest versions in *every* project at once, the user runs, in the dotclaude
repo clone:

```
git pull && ./install.sh        # or .\install.ps1 on Windows
```

That updates `~/.claude/` and all projects pick it up immediately. There is
nothing to refresh inside the project for those five types.

`init.sh --update` inside the project only re-seeds the few **per-project**
files that were missing and drift-reports `settings.local.json.example`:

```
bash ~/.claude/templates/project/init.sh --update [--serena] [--xcode] [--ui]
```

Include `--serena` only if `.mcp.json` exists and has a `serena` entry,
`--xcode` only if it has an `xcode` entry (`grep -q '"xcode"' ./.mcp.json`),
and `--ui` only if it has a `playwright` entry. Re-passing any of them is safe:
all merge idempotently. Omitting a flag on a re-deploy does **not** remove its
server — `.mcp.json` is never rewritten except by the flag that owns the entry.
(`--db` is accepted but a no-op now — the db-inspector agent is central.)

**Offer `--ui` to web-UI projects that predate it.** If `.mcp.json` has no
`playwright` entry but the project clearly has a web UI (a frontend framework in
`package.json` — react/vue/svelte/next/angular/astro —, an `index.html`, or a
`clients/web/` dir), ask via AskUserQuestion whether to add the
Playwright MCP for visual UI verification (the loop `/implement-ui` drives). If
accepted, include `--ui` in the command above and add `mcp__playwright__*` to
the project stub's `permissions.allow` in step 6. If declined, don't ask again
on later re-runs unless the user brings it up. This mirrors §1e's shape:
reconcile an improvement the template gained after the project was deployed,
by asking — never by silently editing.

What `--update` does (implemented in `init.sh`):
- `settings.json` (the per-project stub), `CLAUDE.md`, `CHANGELOG.md`, `docs/*`
  are seeded only if absent — never overwritten (user content).
- `settings.local.json.example` is refreshed if untouched; if the user edited
  it, it is kept and a `DRIFT:` line is emitted.
- With `--serena`, Serena's drift-prevention hooks are *merged* into the
  existing `settings.json` (additive, idempotent, de-duplicated by command — it
  never clobbers your own hooks/permissions). This is the one case where
  `--update` touches an existing `settings.json`, and it's how a project that
  opted into Serena *before* these hooks existed picks them up on a re-run.
- No hooks/agents/skills/rules drift here — those live in `~/.claude/` and are
  updated via `git pull && ./install.sh` in the dotclaude repo.

After the user runs the command and confirms `deploy OK`, run §1c (Drift report),
§1d (CLAUDE.md bullet reconciliation), and §1e (Serena/Graphify improvement
reconciliation), then skip to step 8 (verify).

### Path B: Reconfigure

Re-run the interview phases — load `references/stack-interview.md` (§2 stack, §2b Docker, §2c deployment, §2d versions) and `references/mcp-and-db.md` (§3 MCPs, §4 db) — but **pre-fill each question with the value found in the existing CLAUDE.md / settings.json**. The user just confirms or overrides.

Example: if `## WHAT — Versions` already says `- Database: PostgreSQL 17.2`, when you reach §2d ask "Detected Postgres 17.2 in current CLAUDE.md — keep this?" instead of opening with the full version selector.

When you reach step 5, the deploy command includes `--update`:

```
bash ~/.claude/templates/project/init.sh --update [--serena] [--xcode] [--ui]
```

After deploy OK, step 6 fills only the placeholders that changed (e.g. if the user added Docker, write a new `docker compose exec` prefix on the commands). Do not touch sections the user did not change. Then run §1c, §1d, and §1e (the Serena/Graphify reconciliation applies here too) before step 8.

### Path C: Full re-init from scratch

This destroys local edits in `.claude/`. Before proceeding, ask the user explicitly: "This will delete the current `.claude/`, including any edits of yours. Are you sure?". On confirmation, instruct the user to run `rm -rf .claude` from their terminal (do NOT do it from the skill — destructive ops belong in the user's hands), then continue with the standard first-time flow from §2 (load `references/stack-interview.md`).

`CLAUDE.md`, `CHANGELOG.md`, `.gitignore`, `.mcp.json`, and `.serena/` are NOT touched by this — they survive even path C.

## 1c. Drift report (after Path A or Path B)

After `init.sh --update` finishes, parse any `DRIFT:` lines it emitted to stderr. With the centralized model the per-project surface is tiny, so the only thing that can drift is `settings.local.json.example` (the user edited it and the template changed it). The hooks/agents/skills/rules no longer live in the project, so they never drift here — they are updated centrally via `git pull && ./install.sh` in the dotclaude repo.

If there were no DRIFT lines, tell the user: *"All clean — no divergences in the per-project files."* Move on to §1d.

If `settings.local.json.example` drifted, show the user the diff command so they can reconcile by hand:

```
diff ~/.claude/templates/project/.claude/settings.local.json.example ./.claude/settings.local.json.example
```

Do NOT run the diff yourself — just show the command. The decision of how to reconcile is the user's. (To pick up improvements to the central hooks/agents/skills/rules, remind the user to run `git pull && ./install.sh` in their dotclaude clone — that updates every project at once, no per-project drift involved.)

Move on to §1d.

## 1d. CLAUDE.md bullet reconciliation

`CLAUDE.md` is user-owned and never overwritten, so new bullets added to `CLAUDE.md.template` upstream (e.g. when we add a workflow rule, a new convention, a new "Don't") never reach existing projects. This step offers them as an opt-in addition.

**How to compute the new bullets:**

1. Read `~/.claude/templates/project/CLAUDE.md.template` and the project's `./CLAUDE.md`.
2. For each `## ` section that exists in both files (e.g. `## Workflow`, `## Don't`, `## Portable docs — \`docs/\``), extract bullet lines (lines starting with `- ` at top level of that section).
3. Compute the bullets present in the template version of that section but NOT in the project's version. Compare with a **lenient match** to avoid offering bullets the user already has under slightly different wording:
   - Strip leading `- `, markdown emphasis (`**`, `` ` ``), lowercase, collapse whitespace.
   - A template bullet is "already present" if any project bullet shares the same first 8 normalized words OR if one normalized form starts with the other. Both are noisy but safe — false negatives (offering an already-present bullet) are mildly annoying, false positives (silently skipping a genuinely new bullet) defeat the purpose.
   - When in doubt, prefer offering the bullet — the user can deselect it in the AskUserQuestion.
4. For sections that exist in the template but NOT in the project (e.g. the project predates `## Portable docs — \`docs/\``), treat the entire section as new.

**If nothing is new**, tell the user: *"Your CLAUDE.md already has every convention from the latest template."* and continue to step 8.

**If there are new bullets**, present them via AskUserQuestion as a multiSelect of "bullet labels" (the first 60 chars of each bullet, enough to recognize it). Phrase:

- "The template has new bullets your CLAUDE.md does not include yet. Which ones do you want to add?" (multiSelect)
  - Each option: the truncated bullet text, with a longer description showing the full text and which section it belongs to.

For new whole sections, add one option per section (e.g. *"New section: Portable docs — `docs/` (5 bullets)"*).

For each bullet the user picked, use `Edit` on `./CLAUDE.md` to insert it at the end of the matching section (or, for a new section, insert the whole section between the existing `## ` headers in the right order — match the order in the template). **Do not touch bullets the user did not select.**

After applying, summarize: "Added N bullet(s) to your CLAUDE.md. Review it before committing."

## 1e. Serena / Graphify improvement reconciliation

Projects that opted into Serena *before* recent template improvements miss three
things that newer deploys get. This step detects which apply and offers them.
**Only run this step if the project actually uses Serena** — i.e. `./.mcp.json`
exists and has a `serena` entry. If there is no `serena` entry, skip §1e
entirely (the project never opted in; nothing to reconcile).

**Detection runs AFTER the user's `init.sh --update` deploy**, so if that command
already included `--serena`, gap 1 (the hooks) is already merged and won't be
detected — that is correct, not a bug. §1e exists to catch the gaps that the
deploy does *not* self-heal: a drifted `.mcp.json` (init aborts rather than
overwriting it) and Graphify never being set up. Gap 1 is only ever offered when
the user ran the deploy without `--serena` (e.g. they didn't realize the project
had Serena); in that case the fix is to re-run *with* `--serena`.

Gate first, with the `Bash` tool:

```
test -f ./.mcp.json && grep -q '"serena"' ./.mcp.json && echo HAS_SERENA
```

If that does not print `HAS_SERENA`, skip to step 8.

### Detect the three gaps (read-only)

Run the drift detector from the project root — one command, all checks:

```
python3 ~/.claude/skills/init-project/scripts/detect-drift.py
```

It prints one `KEY=VALUE` per line. **Do not inline these checks as
`python3 -c`**: the central `guard-destructive` hook blocks inline interpreters,
so an inline form fails with exit 2 and the whole gap detection silently dies.
DESIGN.md §5 justifies `python3 -c` inside *hooks* (no PreToolUse runs there),
not inside skills. The script also avoids `jq` (§5).

Map the output to the gaps:

1. **Serena drift-prevention hooks missing.** `SERENA_HOOKS=NO_HOOKS` → gap 1
   applies. (Re-running `init.sh --update --serena` merges them idempotently —
   that is the fix.) `UNKNOWN` means `.claude/settings.json` is missing or
   unparseable: report that to the user instead of assuming either way.

2. **`.mcp.json` outdated.** Either `GRAPHIFY_MCP=GRAPHIFY_BROKEN` (graphify
   still launched via the broken `python -m` form, pre-`uv run` fix) or
   `SERENA_DASHBOARD=DASH_ON` (serena missing `--open-web-dashboard False`, so
   it auto-opens a browser tab) → gap 2 applies.

3. **Graphify never integrated.** `GRAPHIFY_INTEGRATED=GRAPHIFY_ABSENT` → gap 3
   applies: the project has Serena but no `graphify-out/` directory and no
   `## graphify` block in `CLAUDE.md`.

If none of the three gaps apply, tell the user *"Serena and Graphify are already
up to date in this project."* and continue to step 8.

### Offer the applicable gaps (AskUserQuestion, multiSelect)

Build one option per gap that applies:

- "Your project uses Serena but is missing recent template improvements. Which ones do you want to apply?" (multiSelect)
  - **Gap 1** → label "Serena drift-prevention hooks", description "Adds the hooks that keep the model using Serena's tools (merged by re-running the deploy with `--serena`)."
  - **Gap 2** → label "Update `.mcp.json`", description "Fixes the Graphify launch (`uv run` instead of the broken `python` form) and disables Serena's dashboard auto-open. Fixed by re-running the deploy."
  - **Gap 3** → label "Integrate Graphify", description "The graph-first nudge and the auto-rebuild are wired by re-running the deploy with `--serena`; the one step left is building the graph once with `/graphify .`."

### Apply the selected gaps

The three have **different** mechanisms — respect the "skill plans, user executes"
split (DESIGN.md §15): never run `init.sh` or touch `.claude/` files via shell.

- **Gap 1 selected** → the fix is a re-deploy. Tell the user to run, from their
  terminal:
  ```
  bash ~/.claude/templates/project/init.sh --update --serena
  ```
  The hook merge is idempotent (it adds only what is missing) and non-destructive.

- **Gap 2 selected** → a re-deploy fixes it; do **not** hand-edit `./.mcp.json`.
  `init.sh` composes the file per server, so re-running rewrites a drifted
  `serena`/`graphify` entry to the current template form while preserving every
  other key — including servers the user added by hand:
  ```
  bash ~/.claude/templates/project/init.sh --update --serena
  ```
  (This used to be the one place §1e edited a file, back when `--serena` copied
  the whole template and aborted with exit 3 on any difference. It no longer
  does, so the manual edit is gone.) Tell the user the MCP servers must be
  restarted (reopen the session) for the change to take effect.

- **Gap 3 selected** → the gap closes **only** by building the graph once:
  ```
  /graphify .             # builds graphify-out/graph.json (the graphify MCP server needs it)
  ```
  (If `graphify` is not installed: `uv tool install graphifyy` first.)

  This is the step to lead with, because it is the one the detector checks:
  `detect-drift.py` reports GRAPHIFY_PRESENT when `graphify-out/` exists or
  CLAUDE.md carries the Graphify block — and a `--serena` re-deploy creates
  neither. Telling the user only to re-deploy would leave the gap open and
  re-offer it on the next `--update`, forever.

  The supporting pieces come from the `--serena` re-deploy (Gap 1's fix): the
  graph-first nudge (`prefer-graphify`, central) and the auto-rebuild
  (`graphify hook install`). We deliberately avoid `graphify install` itself —
  it appends a raw CLAUDE.md block, drops a per-project skill, and rewrites
  settings.json destructively; see `references/mcp-and-db.md`.

After applying, summarize what changed and what the user still needs to run
manually, then continue to step 8 (verify).
