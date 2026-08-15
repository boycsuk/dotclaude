---
name: implement-ui
description: Implements or modifies a web UI from a design reference (an HTML mockup, a screenshot, or a Claude Design handoff bundle) without drowning in it — extracts design tokens into docs/ui.md first, agrees a component tree, then builds section by section with a screenshot-vs-reference verification loop between sections. Use when the user hands over a mockup or asks to build, replicate, or restyle an interface beyond a trivial tweak.
---

# Implement UI

Replicating a design by pasting the whole mockup into context and coding top to
bottom is how UI work goes wrong: values get invented, sections bleed into each
other, and nothing is verified until the end. This skill enforces the opposite
order — **tokens first, then a confirmed plan, then one section at a time, each
visually verified before the next.**

## 0. Locate the inputs

Identify, asking only for what you cannot detect:

- **The design reference.** One of: an HTML mockup file (Claude Design export or
  similar), one or more screenshots/images, or a Claude Design handoff bundle
  (a zip/directory carrying a component tree + tokens + assets + spec). If the
  user has Claude Design available, suggest its "Hand off to Claude Code" export
  for next time — its bundle already solves the decomposition this skill does by
  hand.
- **The target.** The project's UI stack and where components live. Read 2-3
  sibling components before writing any (rules/workflow.md) so new code matches
  the project's conventions — existing conventions win over mockup idioms.
- **The dev server.** The command that serves the app and its URL (check
  CLAUDE.md's dev command). Needed for step 3's verification loop.

**Never read a large mockup file whole.** Read it in passes: first the
`<style>`/`<head>` block (tokens, step 1), then the body one top-level section
at a time (steps 2-3). The mockup is a quarry, not a listing to transcribe.

## 1. Extract design tokens into docs/ui.md

Before any component code, mine the reference for its design system: colors,
typography scale, spacing scale, radii, elevation/shadows, and component states
(hover/active/disabled/focus).

- Write them into the **Design tokens** section of `docs/ui.md` — that file is
  the project's cross-client visual contract and already defines the table
  format. Replace its placeholder block per the instructions inside it. If
  `docs/ui.md` does not exist (project not deployed from the template), create
  a minimal one with the same section shape.
- Wire the tokens into the project's mechanism: CSS custom properties, Tailwind
  config/theme, or the framework's theme file — whichever the project already
  uses.
- From here on, **implementation code references tokens, never raw hex or raw
  pixels**. A value that appears in the mockup but not in the token tables goes
  into the tables first.

Show the user the extracted tables briefly before moving on — tokens are the
contract everything else builds on, and a wrong extraction poisons every
section.

## 2. Agree the component tree

Enumerate the mockup's top-level sections (header, hero, cards grid, footer…)
and map each to a component file in the project's layout, reusing existing
components wherever one already covers the pattern. Propose the tree and the
build order via AskUserQuestion and let the user confirm or reorder.

If the work adds or renames user-reachable screens, update the **Sections** map
in `docs/ui.md` in the same pass.

## 3. Implement section by section

Work through the confirmed order, **one section per iteration**, and gate each
section on visual verification before starting the next. Never implement two
sections between checks — errors compound silently and context degrades.

Per section:

1. Re-read only that section's fragment of the reference.
2. Implement it using the tokens from step 1 and the project's existing
   components. Include the interaction states the reference shows.
3. **Verify visually** (the gate):
   - If a Playwright-style browser MCP is available (a `playwright` entry in
     `.mcp.json`, deployed by `init.sh --ui`, or the tools are otherwise
     present): navigate to the dev server, resize the viewport to the
     reference's dimensions, take a screenshot, compare it against the
     reference, list the concrete differences (spacing, size, color, alignment,
     missing states), fix them, and re-screenshot. Two or three iterations is
     the normal convergence; do not stop at one.
   - If no browser MCP is available: say so, offer to add it (`claude mcp add
     playwright -- npx -y @playwright/mcp@latest`, or re-deploying with
     `init.sh --update --ui` in template projects), and meanwhile ask the user
     for a screenshot to compare against.
4. Only when the section matches (or the user accepts the remaining
   differences), move to the next.

## 4. Final pass

- Full-page screenshot at a desktop and a mobile width; fix responsive breaks.
- Run `/verify` (tests, typecheck, linter).
- Run `/update-docs`: it reconciles `docs/ui.md` against what actually shipped
  AND catches the `user-stories.md` side — a new user-reachable screen is a
  behavioral contract change, not just a visual one.
- Suggest `/commit` — one commit per coherent chunk, not one per screenshot fix.

## Guardrails

- No new dependencies without explicit confirmation — a mockup's CDN fonts or
  icon packs are a request to make, not a decision to inherit.
- Do not invent values the reference does not define; mark unknowns `TBD` in
  `docs/ui.md` rather than guessing.
- Fidelity to the reference never overrides the project's conventions or
  accessibility basics (semantic elements, focus states, contrast).
