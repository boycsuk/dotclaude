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
bash ~/.claude/templates/project/init.sh --update [--xcode] [--ui] [--codebase-memory] [--lsp=<plugin>]
```

On native Windows (SKILL.md step 1), every `init.sh` command in this file is
`powershell -NoProfile -ExecutionPolicy Bypass -File "$HOME\.claude\templates\project\init.ps1"`
with the same flags.

Include `--xcode` only if `.mcp.json` has an `xcode` entry
(`grep -q '"xcode"' ./.mcp.json`), `--ui` only if it has a `playwright`
entry, and `--codebase-memory` only if it has a `codebase-memory-mcp` entry. Re-passing any of them is safe:
all merge idempotently. Omitting a flag on a re-deploy does **not** remove its
server — `.mcp.json` is never rewritten except by the flag that owns the entry.

**Many projects at once.** To refresh every dotclaude project under a folder
(for example after a dotclaude change that retires an artifact), the user runs,
from their terminal:

```
bash ~/.claude/templates/project/init.sh --update --recursive ~/projects
```

It lists each project with the flags derived from its `.mcp.json`, the
obsolete hooks it prunes, the obsolete MCP servers it removes (with their
`mcp__<name>` permissions) and the obsolete directories it only reports, then
asks before changing anything (`--dry-run` shows the list only, `--yes` skips
the question). Mention it when the user has several projects to update; it does
not replace §1d/§1e, which stay per project.

**Offer `--lsp=<plugin>` to code projects that predate it.** Read
`enabledPlugins` in `.claude/settings.json`. If the project's language has an
official plugin in `~/.claude/templates/project/lsp-plugins.json` and it is not
there, ask via AskUserQuestion whether to add it (see
`references/mcp-and-db.md` §3b for the binary check), and include the flag in
the command above if accepted. Same rule as below: ask once, never edit
silently.

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
  it, it is kept (§1c reports it).
- Hook entries that point at hooks dotclaude no longer ships (listed in
  `templates/project/obsolete.json`) are pruned from `.claude/settings.json`
  and `settings.local.json` — every deploy does this, not only `--update`. It
  is the one case where a deploy edits an existing settings file, and it only
  ever removes entries whose script is already gone. MCP servers in the
  manifest are removed only with `--remove-obsolete-mcp` (the user's choice in
  §1e; `--recursive` always passes it); directories are never removed.
- No hooks/agents/skills/rules drift here — those live in `~/.claude/` and are
  updated via `git pull && ./install.sh` in the dotclaude repo.

After the user runs the command and confirms `deploy OK`, run §1c (Drift report),
§1d (CLAUDE.md bullet reconciliation), and §1e (obsolete-artifact
reconciliation). If `docs/conventions.md` still contains `{{WORKING_LANGUAGE}}`
(the deploy just seeded it into a project that predates it), fill it as
SKILL.md step 6 describes. Then skip to step 8 (verify).

### Path B: Reconfigure

Re-run the interview phases — load `references/stack-interview.md` (§2 stack, §2b Docker, §2c deployment, §2d versions) and `references/mcp-and-db.md` (§3 MCPs, §4 db) — but **pre-fill each question with the value found in the existing CLAUDE.md / settings.json**. The user just confirms or overrides.

Example: if `## WHAT — Versions` already says `- Database: PostgreSQL 17.2`, when you reach §2d ask "Detected Postgres 17.2 in current CLAUDE.md — keep this?" instead of opening with the full version selector.

When you reach step 5, the deploy command includes `--update`:

```
bash ~/.claude/templates/project/init.sh --update [--xcode] [--ui] [--codebase-memory] [--lsp=<plugin>]
```

After deploy OK, step 6 fills only the placeholders that changed (e.g. if the user added Docker, write a new `docker compose exec` prefix on the commands). Do not touch sections the user did not change. Then run §1c, §1d, and §1e before step 8.

### Path C: Full re-init from scratch

This destroys local edits in `.claude/`. Before proceeding, ask the user explicitly: "This will delete the current `.claude/`, including any edits of yours. Are you sure?". On confirmation, instruct the user to run `rm -rf .claude` from their terminal (do NOT do it from the skill — destructive ops belong in the user's hands), then continue with the standard first-time flow from §2 (load `references/stack-interview.md`).

`CLAUDE.md`, `CHANGELOG.md`, `.gitignore`, and `.mcp.json` are NOT touched by this — they survive even path C.

## 1c. Drift report (after Path A or Path B)

The deploy prints its `DRIFT:` lines in the user's terminal, which this session never sees, so read `SETTINGS_EXAMPLE_DRIFT` from `python3 ~/.claude/skills/init-project/scripts/detect-drift.py` instead (`YES` = edited and different from the template, `NO`, `ABSENT`, `UNKNOWN`). With the centralized model the per-project surface is tiny, so the only thing that can drift is `settings.local.json.example` (the user edited it and the template changed it). The hooks/agents/skills/rules no longer live in the project, so they never drift here — they are updated centrally via `git pull && ./install.sh` in the dotclaude repo.

If it is not `YES`, tell the user: *"All clean — no divergences in the per-project files."* Move on to §1d.

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

## 1e. Obsolete-artifact reconciliation

dotclaude occasionally stops shipping something a project was deployed with
(Serena and Graphify were the first). `templates/project/obsolete.json` lists
those artifacts. The deploy already pruned the dead **hook entries** on its own;
this step handles what it deliberately leaves to the user: obsolete **MCP
servers** in `.mcp.json` and obsolete **directories**.

Run the drift detector from the project root:

```
python3 ~/.claude/skills/init-project/scripts/detect-drift.py
```

It prints one `KEY=VALUE` per line. **Do not inline these checks as
`python3 -c`**: the central `guard-destructive` hook blocks inline interpreters,
so an inline form fails with exit 2 and the detection silently dies. DESIGN.md
§5 justifies `python3 -c` inside *hooks* (no PreToolUse runs there), not inside
skills.

- `OBSOLETE_HOOKS=<n>` with n > 0 → the deploy has not run since the hook was
  retired (or the user skipped it). Tell them to re-run the `init.sh --update`
  command from Path A; it prunes them.
- `OBSOLETE_MCP=<names>` → servers dotclaude no longer configures, still in
  `.mcp.json`.
- `OBSOLETE_FILES=<paths>` → leftover directories (e.g. `.serena`,
  `graphify-out`).
- `UNKNOWN` → the manifest is missing (re-run `./install.sh` in the dotclaude
  clone); say so instead of assuming either way.

If all three are empty / `0`, tell the user *"No obsolete dotclaude artifacts
in this project."* and continue to step 8.

Otherwise ask via AskUserQuestion (multiSelect), one option per server and per
directory, each description giving the `reason` from `obsolete.json`:

- "These were deployed by an older dotclaude and are no longer maintained. Which do you want to remove?"

For the selected **servers**, do not edit by hand: print the deploy command
with `--remove-obsolete-mcp` for the user to run from their terminal
(`bash ~/.claude/templates/project/init.sh --update --remove-obsolete-mcp`
plus the project's usual flags). It removes the servers from `.mcp.json` and
every reference to them — `allow`/`ask`/`deny` rules and the
`enabledMcpjsonServers`/`disabledMcpjsonServers` entries in
`settings.local.json` — which a hand edit kept missing. It removes every
obsolete server, so if the user selected only some, tell them which others it
will also drop and let them decide. Tell the user to reopen the session so the
MCP change takes effect.
If the user still has the binary installed, mention it can be uninstalled
(e.g. `uv tool uninstall serena-agent`, `uv tool uninstall graphifyy`) — their
call, never yours.

For each selected **directory**, print the removal command for the user to
run from their terminal (`rm -r .serena`) — never delete it from the skill.
Unselected items stay untouched and will be offered again on the next
`--update`.

After applying, summarize what changed and what the user still needs to run
manually, then continue to step 8 (verify).
