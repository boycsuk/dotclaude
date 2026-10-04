# Making a Design canvas that hands off cleanly

The Design type's own instructions (the create result carries them) govern the
file format. This page adds the structure the handoff needs: without it,
`docs/design/` has no parameters to read and the spec turns into guesses.

Start the canvas with the Artifact tool: `quickstart` with intent `design`,
then publish with the `type_url` it returns and a `title`.

## Rules

1. **Reuse the project's tokens.** If `docs/ui.md` already holds live tokens
   (its placeholder comment is gone), the canvas uses exactly those values.
   Otherwise commit to a small system, taken from the chosen style when
   `design-research.md` ran; it becomes the skill's token step.
   Inline styles use values from the scale only, so every size maps to one
   token.
2. **Screens and components are separate artboards.** Every element that
   appears more than once or has options (table, form, card, nav bar, modal,
   button with variants) is its own `<Name>.dc.html`, PascalCase, named as
   the code will name it, and screens mount it with
   `<dc-import name="Name" …>`. A screen artboard holds layout, `dc-import`s
   and one-off content only.
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
5. **Variants are drawn.** A component with variants or states gets a
   `<Name>Variants.dc.html` artboard that mounts it once per variant and
   state, each labelled. A component that shows data also mounts it with no
   items, one item, many items and text longer than its space, so the
   overflow rule is visible.
6. **Pages split the canvas.** `canvas.json` gets two `pages`: `screens`
   (the screen artboards) and `components` (each component and its variants
   sheet), with every `boards` entry assigned to one.
7. **The narrow size is visible.** Screens are fluid pages per the Design
   type's rules; for a desktop app, each screen's frame is the window's
   default size. The narrow size is a phone width (390 px) for web and the
   minimum window size for desktop. A screen whose structure changes there
   beyond wrapping (a side menu that collapses into a button, a table that
   turns into cards) also gets a `<Screen>Narrow.dc.html` artboard at that
   size.
8. **Content is real.** Copy is the final text, written literally in the
   markup, not placeholder or lorem; a value nobody has decided is a
   bracketed placeholder like `[EMPTY STATE TEXT]`, which the spec turns into
   a `TBD`. Sample data has realistic formats and lengths.
9. **What cannot be drawn is noted.** Keyboard behaviour, focus on open and
   close, and when an event fires go in a sticky note (`notes` in
   `canvas.json`) beside the artboard they belong to.

## Done

The design is done when the user approves the canvas, not when it is
published. Then return to the skill's token step with the canvas link.

## A canvas that does not follow these rules

A canvas made elsewhere may draw its components inline. Before writing the
spec, list what breaks the rules (inline patterns, options with no
`data-props`, missing variants) and offer to restructure the canvas to them.
It is the user's design: change it only on a yes. On a no, write the spec
anyway, with those parameters as `TBD`.
