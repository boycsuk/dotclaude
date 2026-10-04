---
name: update-docs
description: Updates docs/ and design/ so they reflect contract changes in the current diff — backend endpoints, user-facing capabilities (user stories), and the design (screens, design tokens, and component or screen specs, written back to the Design canvas when the code moved first). Use proactively before committing when a task may have changed a contract (a new/changed endpoint, a screen or component, a token, or a user-facing capability). Proposes the edits for confirmation before writing.
allowed-tools: Bash(git diff:*) Bash(git status:*) Glob Read Edit Write
---

# Update docs

The portable docs under `docs/` describe **the system as it is now** — what
each component exposes to the rest. They are the only context available to
tools that can only see one slice of the repo (Xcode workspaces, sandboxed
editors, embedded subdirs). They are useful only if they are **true**.

Your job: make `docs/` (and `design/`, when the project has one) match what the diff actually shipped. Nothing more,
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
When the diff touches UI code, also list `design/` (`Glob: design/**/*`): it is
the project's design (`/implement-ui`'s `references/design-spec.md`). A
project with a legacy `docs/ui.md` and no `design/` keeps maintaining
`docs/ui.md` for now; say once that `/implement-ui` can migrate it.

**When `design/README.md` names a canvas** and the diff touches UI, compare the
canvas's version (`Artifact` `list`, `scope: "files"`, its `url`) with the
`Canvas version` line. A different one means the canvas was edited on the web
since the specs were written: say so and point at `/implement-ui` to regenerate
them before any spec edit here.

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
   - **`design/README.md` and `design/tokens.json` (the visual + navigational
     contract)** — added/removed/renamed top-level section/screen, or changed
     its purpose (`## Sections` and the screen index); added/removed/renamed
     a design token (color, typography, spacing, radius, elevation) or changed
     its value (`tokens.json`, in the shape `/implement-ui`'s
     `references/design-tokens.md` defines). Do NOT record which endpoints a
     section consumes (that lives in `backend.md`).
   - **`user-stories.md` (the behavioral contract)** — the user can now do
     something new, can no longer do something, or achieves it differently.
     Write it as a platform-agnostic story (parity by default); add a
     `Platform exception:` line only if a client genuinely differs. A feature
     usually touches all three: the capability in `user-stories.md`, the
     screen in `design/`, the endpoints in `backend.md` — keep each lens in its
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
   - **`design/` component and screen specs** — find the spec whose `Code:`
     line names a changed file. If the diff makes that screen or component
     differ from its spec (a parameter added or dropped, a region moved, a
     size changed):
     - **with a canvas**, the canvas is the source and never trails the code:
       propose the write-back first (`/implement-ui`'s
       `references/design-canvas.md`, Write-back: edit the artboard,
       republish, record the version, regenerate the spec). Propose an
       `## Accepted deviations` line instead only for what a canvas cannot
       draw, or when the user declines the write-back;
     - **without a canvas**, edit the spec to describe the code;
     - a file that moved or was renamed updates the `Code:` line;
     - a new component or screen with no spec gets one, written as
       `references/design-spec.md` says, status `implemented`.
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

3. **If there is a contract change**, first show the proposed edit for each
   affected `docs/` or `design/` file (the section and the new text) and confirm via
   AskUserQuestion — apply / adjust / skip. The description promises that, and
   docs are shared surface. Then edit with the `Edit` tool. Rules:
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
     structure of `docs/backend.md` or `docs/user-stories.md`,
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
  section appears in `## Sections` of `design/README.md` (or the legacy
  `docs/ui.md`). Add a one-liner for any missing one. If the diff touched a
  theme/style file (CSS variables, SwiftUI Color extensions, Compose theme,
  Tailwind config), confirm `design/tokens.json` holds every token it defines,
  under the same names and values.
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
- which `docs/` or `design/` file(s) you edited (or "none");
- anything ambiguous you had to guess — flag it so the user can correct.

Do not run `git add`, do not commit. The user runs `/commit` next.
