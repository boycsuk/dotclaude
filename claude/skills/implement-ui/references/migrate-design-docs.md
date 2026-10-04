# Migrating existing design documentation into docs/design/

Projects older than `docs/design/` keep their design wherever it grew: a
`docs/ui.md` from the old template (often a full UI spec over a thousand lines
long), a `STYLEGUIDE.md`, a root `design/` folder of per-screen notes and HTML
mockups, a design section inside another doc. The migration moves every line
of design content into `docs/design/` (`design-spec.md`), where each piece has
one place, without inventing anything and without losing anything.

## 1. Find the candidates

At step 0 of the skill, before any design work:

1. **By name.** Run `python3 ~/.claude/skills/init-project/scripts/detect-drift.py`
   and read `LEGACY_DESIGN_DOCS`: the Markdown files whose name reads as design
   (`ui`, `design`, `style`, `styleguide`, `theme`, `tokens`, `brand`,
   `components`, `screens`, `ux`, `wireframes`, `mockups`), and design-named
   folders that hold Markdown (listed with a trailing `/`), outside
   `docs/design/`, dependencies and build output.
2. **By content.** Read the headings of the other Markdown files in `docs/`
   and the root (outline only, never whole) and add those whose sections
   describe the design: palette, typography, spacing, screens, components,
   layouts, keys, copy rules. A file that only touches design in one section is
   a candidate for that section alone. Also follow links: a doc that says where
   the design lives ("see design/…") names more candidates.

Nothing found: say nothing and continue. Otherwise ask through
AskUserQuestion (multiSelect), one option per candidate, each with one line
on why it reads as design (its name, or the sections that matched), plus
**Not now**:

- **Selected candidates** go through this procedure, then the request.
- **Not now**: the request runs with what exists. The skill reads tokens and
  sections from those files, writes nothing to `docs/design/`, and keeps their
  format. Say that `/init-project --update` keeps listing them.

## 2. Outline first

Never read a candidate whole. List each file's headings with their line
ranges (for a folder, its files first), then read one top-level section at a
time while you classify it.

## 3. Classify every section

| What the section holds | Where it goes |
|------------------------|---------------|
| Tokens (colors, type, spacing, radii, elevation, z-index, motion) | `docs/design/tokens.json`, converted to the shape in `design-tokens.md`; a Light/Dark column pair becomes two themes |
| An overview of the product's look | `docs/design/README.md` → `## Overview` |
| A sections/screens list | `docs/design/README.md` → `## Sections`, each linked to its screen spec |
| One screen, page, window or view | `docs/design/screens/<kebab>/README.md` |
| A piece used from more than one place, or with options (a dialog, a panel type, a row, a form) | `docs/design/components/<kebab>/README.md` |
| A region of a single screen | that screen's spec (`## Layout`, `## Content`) |
| Rules for every screen (global keys, truncation, copy voice, error and progress reporting, style roles that are not tokens) | `docs/design/README.md` → `## Conventions` |
| Keys, copy or states of one screen or component | that spec's `## Keyboard and focus`, `## Copy`, `## States` |
| Where an older design lived, platform limits, rationale | `docs/design/README.md` → `## Overview`, kept short |
| Non-design content in a mixed file (an endpoint, a user story) | stays where it is |

Names come from the code (the component's or screen's identifier, in kebab
case), so the spec, the code and any future canvas agree, whatever language or
numbering the old files used.

**Files that are not Markdown** in a candidate folder (HTML mockups, images,
exported frames) are references, not specs: leave them where they are, list
them under `## References` in `docs/design/README.md` with what each shows,
and let the user decide in step 6 whether to keep them.

## 4. Show the mapping, then write

Present the plan as one table (each source file and heading → its destination
file and section) and confirm it through AskUserQuestion: apply / adjust. Then
write:

- **Verbatim where it is already specific.** Copy, key bindings, values and
  rules move as written; only their place changes. Do not rephrase what the
  old file states precisely, and keep its language for copy (the strings the UI
  shows); spec prose around it is English.
- **Fill the spec's other sections from what the files say**, and leave a
  section empty or `TBD` when they say nothing. Never invent a parameter, a
  size or a state to fill the template.
- **`Code:`** on every spec: find the source files that implement the piece
  (search the code for its identifier) and list them. One you cannot find is
  `TBD` and goes in `## Open questions`.
- **`## Acceptance`**: one line per behaviour the old files state (a key does
  X, a long name truncates, an empty list shows Y). Nothing beyond what they
  state.
- **Status `implemented`** in the index: the code exists, but nothing has been
  verified against a drawing. `docs/design/README.md` says `Canvas: none`.
- Tokens the code uses but no old file listed: read the theme file and add
  them, marked in their `usage` as found in code.

## 5. Check coverage

Walk the outline from step 2 and name, for every heading, the file and section
it went to. Count tokens before and after. A heading with no destination is a
gap: fix it, never drop it.

## 6. Retire the old files

Show the coverage list and ask through AskUserQuestion, per source, whether
to delete it (for a mixed file: remove its design sections only; for a folder:
its Markdown, and separately whether to keep its mockups). On a yes, apply it
and point the project's own references at `docs/design/`: its CLAUDE.md (the
`docs/` contract line and the `ui.md` bullet of the contract-change list),
`docs/README.md` if it is the older seed, and any link to the old files. On a
no, keep it and say that the two now overlap until it is removed.

Then continue with the request at step 1 of the skill, and suggest a commit
for the migration alone first, so it is reviewable apart from new work.
