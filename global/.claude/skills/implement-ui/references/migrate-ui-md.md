# Migrating a legacy docs/ui.md into docs/design/

Projects deployed before `docs/design/` existed keep their visual contract in
`docs/ui.md`. Some hold only tokens and a sections list; many grew into a full
UI spec (screens, panels, modals, keys, copy) over a thousand lines long. The
migration moves every line of it into `docs/design/` (`design-spec.md`), where each
piece has one place, without inventing anything and without losing anything.

## When

At step 0 of the skill, when `docs/ui.md` exists. Ask through
AskUserQuestion before anything else:

- **Migrate now** (recommended): this procedure, then the request.
- **Not now**: the request runs the old way. Tokens and sections are read from
  and written to `docs/ui.md`, no specs are written, and nothing is created in
  `docs/design/`. Say that `/init-project --update` keeps reporting it.

## 1. Outline first

Never read the file whole. List its headings with their line ranges, then read
one top-level section at a time while you classify it.

## 2. Classify every section

| What the section holds | Where it goes |
|------------------------|---------------|
| Tokens (colors, type, spacing, radii, elevation, z-index, motion) | `docs/design/tokens.json`, converted to the shape in `design-tokens.md`; a Light/Dark column pair becomes two themes |
| The overview paragraph | `docs/design/README.md` → `## Overview` |
| The sections/screens list | `docs/design/README.md` → `## Sections`, each linked to its screen spec |
| One screen, page, window or view | `docs/design/screens/<kebab>/README.md` |
| A piece used from more than one place, or with options (a dialog, a panel type, a row, a form) | `docs/design/components/<kebab>/README.md` |
| A region of a single screen | that screen's spec (`## Layout`, `## Content`) |
| Rules for every screen (global keys, truncation, copy voice, error and progress reporting, style roles that are not tokens) | `docs/design/README.md` → `## Conventions` |
| Keys, copy or states of one screen or component | that spec's `## Keyboard and focus`, `## Copy`, `## States` |
| Where an older design lived, platform limits, rationale | `docs/design/README.md` → `## Overview`, kept short |

Names come from the code (the component's or screen's identifier, in kebab
case), so the spec, the code and any future canvas agree.

## 3. Show the mapping, then write

Present the plan as one table (each source heading → its destination file and
section) and confirm it through AskUserQuestion: apply / adjust. Then write:

- **Verbatim where it is already specific.** Copy, key bindings, values and
  rules move as written; only their place changes. Do not rephrase what the
  old file states precisely.
- **Fill the spec's other sections from what the file says**, and leave a
  section empty or `TBD` when it says nothing. Never invent a parameter, a
  size or a state to fill the template.
- **`Code:`** on every spec: find the source files that implement the piece
  (search the code for its identifier) and list them. One you cannot find is
  `TBD` and goes in `## Open questions`.
- **`## Acceptance`**: one line per behaviour the old file states (a key does
  X, a long name truncates, an empty list shows Y). Nothing beyond what it
  states.
- **Status `implemented`** in the index: the code exists, but nothing has been
  verified against a drawing. `docs/design/README.md` says `Canvas: none`.
- Tokens the code uses but the old file never listed: read the theme file and
  add them, marked in their `usage` as found in code.

## 4. Check coverage before deleting

Walk the outline from step 1 and name, for every heading, the file and
section it went to. Count tokens before and after. A heading with no
destination is a gap: fix it, never drop it.

## 5. Retire docs/ui.md

Show the coverage list and ask through AskUserQuestion whether to delete
`docs/ui.md`. On a yes, delete it and point the project's own references at
`docs/design/`: its CLAUDE.md (the `docs/` contract line and the `ui.md` bullet of
the contract-change list), `docs/README.md` if it is the older seed, and any
link to `docs/ui.md` in other docs. On a no, keep it and say that the two now
overlap until it is removed.

Then continue with the request at step 1 of the skill, and suggest a commit
for the migration alone first, so it is reviewable apart from new work.
