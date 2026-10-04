# The project's Design canvas

The Design type's own instructions (a create or read result carries them)
govern the file format. This page adds what keeps a project's design ordered
and reusable: one canvas, laid out like `design/`, with components that are
edited in one place.

## One canvas per project

A project has at most one canvas, named in `design/README.md`. Every design
request extends it: a second screen is new artboards on the same canvas,
never a new artifact. Only when `design/README.md` names no canvas, start one:
the Artifact tool's `quickstart` with intent `design`, then publish with the
`type_url` it returns and the project's name as `title`. Write its link into
`design/README.md` at once.

The canvas is never stored in the repo: no `.dc.html`, no `canvas.json`.
Edit it in a folder under the scratchpad directory and publish from there.

## Layout

Artboard paths under `project/` mirror `design/`, and every artboard belongs to
one of three pages:

| Page | Artboards |
|------|-----------|
| `components` | `components/<kebab>/<Pascal>.dc.html`, and its `components/<kebab>/<Pascal>Variants.dc.html` |
| `screens` | `screens/<kebab>/<Pascal>.dc.html`, and its `screens/<kebab>/<Pascal>Narrow.dc.html` |
| `explorations` | `explorations/<yyyy-mm-dd>-<slug>/<Pascal>.dc.html` |

`<kebab>` is the folder of the matching spec in `design/` (`data-table`,
`checkout`); `<Pascal>` is the name the code gives it (`DataTable`). Stems are
unique across the canvas, so an exploration's artboard gets a distinct name
(`CheckoutOneStep`, not a second `Checkout`).

## Before drawing anything: reuse

1. Read `design/README.md`'s component index and the spec of every component
   the request could use.
2. For each region of the new screen, pick in this order: an existing
   component as it is; an existing component with a new parameter value; an
   existing component extended with a new parameter or variant (edit its
   artboard, its variants sheet and its spec); only then a new component.
3. A pattern the new screen repeats, or that an existing screen already draws
   inline, becomes a component now, and the screens that drew it inline mount
   it instead.

Say which components you reused, extended or created before drawing.

## Rules

1. **Reuse the project's tokens.** When `design/tokens.json` exists, the
   canvas uses exactly those values (installed as `design-tokens.md` says).
   Otherwise commit to a small system, taken from the chosen style when
   `design-research.md` ran; it becomes `design/tokens.json`. Inline styles
   use values from the scale only, so every size maps to one token.
2. **One piece, one place.** Every element that appears more than once or has
   options (table, form, card, nav bar, modal, button with variants) is its own
   component artboard, and screens mount it with `<dc-import name="Name" …>`.
   A screen artboard holds layout, `dc-import`s and one-off content only.
   Changing a component means editing its artboard, never restyling it inside a
   screen.
3. **Every option is declared.** A component declares each of its options in
   its `data-props`: booleans for switches (`pagination`, `selectable`),
   enums for variants (`size`: `sm|md|lg`), numbers with `min`/`max`/`step`
   (`pageSize`), and `editor: null` with a `tsType` for data and callbacks
   (`columns: Column[]`, `onSelect`); name types the way the target
   language will, since the parameters table carries them into the code.
   States the component has go in a `state` enum
   (`default|loading|empty|error`). `renderVals()` reads each
   with a fallback to its default, and the markup visibly changes with each
   value: a `pagination` flag that draws nothing is not a parameter. The
   Design type asks for few tweaks; that holds for screens, while on a
   component artboard its parameters are its levers, so declare them all.
4. **Every call site is explicit.** Each `<dc-import>` passes every
   parameter the screen relies on, even when it equals the default, so the
   spec records how each screen configures each component.
5. **Variants are drawn.** A component with variants or states gets its
   variants sheet, which mounts it once per variant and state, each labelled.
   A component that shows data also mounts it with no items, one item, many
   items and text longer than its space, so the overflow rule is visible.
6. **The narrow size is visible.** Screens are fluid pages per the Design
   type's rules; for a desktop app, each screen's frame is the window's
   default size. The narrow size is a phone width (390 px) for web and the
   minimum window size for desktop. A screen whose structure changes there
   beyond wrapping (a side menu that collapses into a button, a table that
   turns into cards) also gets its narrow artboard.
7. **Content is real.** Copy is the final text, written literally in the
   markup, not placeholder or lorem; a value nobody has decided is a
   bracketed placeholder like `[EMPTY STATE TEXT]`, which the spec turns into
   a `TBD`. Sample data has realistic formats and lengths.
8. **What cannot be drawn is noted.** Keyboard behaviour, focus on open and
   close, and when an event fires go in a sticky note (`notes` in
   `canvas.json`) beside the artboard they belong to.

## Explorations

A design that tries something out, or is not yet part of the product, is an
exploration: its artboards go under `explorations/<yyyy-mm-dd>-<slug>/` on the
`explorations` page. It may mount the real components. It gets no spec and no
row in `design/README.md`, and its code is never built.

- **Promote**: move the artboard into `screens/` or `components/` (rename it if
  its stem clashes), write its spec, add its index row as `designed`.
- **Discard**: delete its artboards.

Ask which one when an exploration is approved or abandoned; never leave it to
drift into the screens page.

## The published version

`design/README.md` records the canvas version the spec was last written from:
the `version <id>` that `Artifact` `list` with `scope: "files"` and the
canvas `url` prints. After every publish, list again and write the new id.

Before any design work, list it and compare. A different id means the canvas
was edited on the web since the spec was written: read the artboards that
changed (re-read the ones the spec covers and compare), regenerate their specs
(`design-spec.md`), and only then start the new work.

## Write-back: when the code changed first

A change made in code to something designed (a parameter added, a region
moved, a size changed) goes back into the canvas, so the drawing stays the
truth:

1. Read the artboard (and its variants sheet) from the canvas.
2. Copy it under one scratch `<root>` at its canvas path, edit it to match the
   code, and publish only those files.
3. Record the new version in `design/README.md` and regenerate that spec.

Only what a canvas cannot draw (an animation, a platform widget, a behaviour
under load) becomes an `## Accepted deviations` line instead.

## Done

The design is done when the user approves the canvas, not when it is
published. Then return to the skill with the canvas link.

## A canvas that does not follow these rules

A canvas made elsewhere may draw its components inline, use flat paths, or
miss pages. Before writing the spec, list what breaks the rules (inline
patterns, options with no `data-props`, missing variants, paths outside the
layout) and offer to restructure the canvas to them. It is the user's design:
change it only on a yes. On a no, write the spec anyway, with those parameters
as `TBD`.
