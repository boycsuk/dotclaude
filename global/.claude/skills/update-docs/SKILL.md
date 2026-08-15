---
name: update-docs
description: Updates docs/ so it reflects contract changes in the current diff — backend endpoints, UI sections/design tokens, and user-facing capabilities (user stories). Use proactively before committing when a task may have changed a contract (a new/changed endpoint, a UI section, or a user-facing capability). Proposes the doc edits for confirmation before writing.
allowed-tools: Bash(git diff:*) Bash(git status:*) Glob Read Edit Write
---

# Update docs

The portable docs under `docs/` describe **the system as it is now** — what
each component exposes to the rest. They are the only context available to
tools that can only see one slice of the repo (Xcode workspaces, sandboxed
editors, embedded subdirs). They are useful only if they are **true**.

Your job: make `docs/` match what the diff actually shipped. Nothing more,
nothing less.

## Inputs

### Current diff (staged + unstaged)

```!
git diff --cached
```

```!
git diff
```

> Staged + unstaged together cover the same ground as `git diff HEAD`, which
> exits 128 in a repo with no commits and would abort the whole skill (the same
> fix `changes` and `audit` carry).

### Files added or removed

```!
git status --porcelain
```

Untracked files appear by NAME only — their content is in no diff, and a new
file is the single most common source of a new contract (a new router, a new
screen, a new worker). `Read` any untracked file that looks like a contract
surface before classifying it. Do not describe one you have not read, and do
not skip it either.

### Current docs

List `docs/` with the **Glob tool** (`Glob: docs/*`) — portable across Unix and
Windows, unlike `ls ... 2>/dev/null`. An empty result just means no docs yet.

Then `Read` (the tool, not `cat`) the specific `docs/*.md` file(s) the change
touches — usually one or two. Do not bulk-read every doc: read only what you
will edit, plus any file the coverage audit below points you at.

## How to decide what to do

1. **Classify the diff.** Walk through the diff and decide if it changes a
   contract another part of the system relies on. The three docs answer
   different questions; route each change to the right one:
   - **`backend.md` (the API contract)** — added/removed/renamed endpoint;
     changed request body shape; changed response shape; changed auth
     requirement; changed error code semantics; new shared error model.
   - **`ui.md` (the visual + navigational contract)** — added/removed/renamed
     top-level section/screen, or changed its purpose; added/removed/renamed
     a brand design token (color, typography, spacing, radius, elevation) or
     changed its value. Do NOT record which endpoints a section consumes
     (that lives in `backend.md`) or component-level detail (that stays in
     source).
   - **`user-stories.md` (the behavioral contract)** — the user can now do
     something new, can no longer do something, or achieves it differently.
     Write it as a platform-agnostic story (parity by default); add a
     `Platform exception:` line only if a client genuinely differs. A feature
     usually touches all three docs: the capability in `user-stories.md`, the
     screen in `ui.md`, the endpoints in `backend.md` — keep each lens in its
     own file, do not duplicate the detail.
   - **`conventions.md` (the coding-convention mirror)** — the diff changed a
     rule file (added/removed/reworded a convention) — either the developer's
     personal `~/.claude/rules/*.md` or a project-local `.claude/rules/*.md`.
     Reflect it in `docs/conventions.md`, which per DESIGN.md §17 is the
     **canonical, repo-versioned copy** every contributor and non-Claude tool
     reads; the rules file is the copy Claude Code loads and is not checked in,
     so neither takes precedence — reconcile by hand. Keep the mirror a concise
     summary, not a paste. This is the one doc driven by a config change rather
     than a product change.
   - **Cross-component** — a new contract producer or consumer appears
     (e.g. a new bot, CLI, mobile target, webhook feed) that warrants its own
     `docs/` file.
   - **The root README** — the diff changed something the README states:
     an install step, a command or flag, a requirement, a usage example,
     the project's one-line description. Do not edit it here; flag it and
     point at `/readme`, which owns the public-README standard (structure,
     anti-slop rules, what must never leak into a public repo).

   The following do NOT count, even if they touch backend/frontend code:
   - internal refactors, renamed private helpers, logging, formatting;
   - tests, build/CI config, dependency bumps with no behavior change;
   - bug fixes that restore the previously documented behavior.

2. **If nothing in the diff is a contract change**, write exactly:
   `update-docs: nothing to update.`
   Then stop. Do not edit any file. Do not invent changes to justify the
   invocation.

3. **If there is a contract change**, edit the affected `docs/*.md` file(s)
   with the `Edit` tool. Rules:
   - Only touch the sections that need to change. Leave the rest verbatim.
   - Keep the existing structure and tone of the file. Match its style.
   - **Coverage over depth.** Every new capability must appear, even if
     as a single line. A one-line entry that exists beats a perfect entry
     that does not. Never skip an endpoint/section because "it's trivial"
     or "the name is self-explanatory" — if it is a capability of the
     system, it must be listed.
   - Be concise per entry: bullets and small tables over paragraphs. No
     code dumps — short JSON shape examples are fine.
   - English only (codebase rule). No emojis.
   - If the diff *removed* an endpoint or section, **remove** its entry —
     do not leave it with a "(deprecated)" note unless the code still
     keeps it as deprecated.
   - If a new contract producer/consumer appears and there is no
     corresponding file yet, create one (e.g. `docs/bot.md`). Mirror the
     structure of `docs/backend.md`, `docs/ui.md`, or `docs/user-stories.md`,
     whichever is closest in role, and give it the same kind of self-contained
     maintenance header.

### Coverage audit (drift check)

Even when the diff itself looks small, the docs may already be missing
older capabilities that were never written down. So after applying the
diff-driven edits, do a quick cross-check on the touched files:

- Backend: skim the route registration / router file(s) (e.g. `main.rs`,
  `urls.py`, `app.ts`) and confirm every registered route appears in
  `docs/backend.md`. Add a one-liner for any missing one.
- UI: skim the top-level navigation/router and confirm every user-reachable
  section appears in `docs/ui.md`. Add a one-liner for any missing one. If the
  diff touched a theme/style file (CSS variables, SwiftUI Color extensions,
  Compose theme, Tailwind config), confirm the `## Design tokens` section
  reflects the current palette / typography / spacing.
- User stories: if the diff added or changed a user-facing capability,
  confirm there is a story for it in `docs/user-stories.md`. Add a one-liner
  story for any capability that the change exposes but that is not yet listed.

Only audit the file(s) the current diff already touched — do not turn
this into a full repo sweep. The goal is to fix drift in passing, not
to backfill the entire history in one go.

4. **Do not edit `docs/README.md`.** It describes the convention itself,
   not the project. Updating it is a meta-change that belongs in a
   separate explicit task.

5. **Do not touch `CHANGELOG.md`.** `/commit` handles that. These docs
   describe the current state of the system; `CHANGELOG.md` describes
   its history.

## Output

After your edits (or the "nothing to update" message), summarize in 1-3
bullets:
- what contract change you detected (or "none");
- which `docs/` file(s) you edited (or "none");
- anything ambiguous you had to guess — flag it so the user can correct.

Do not run `git add`, do not commit. The user runs `/commit` next.
