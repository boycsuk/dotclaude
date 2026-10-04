# Design tokens: docs/design/tokens.json

`docs/design/tokens.json` holds every color, type style, spacing step, radius and
shadow the product uses: names, values per theme, and when to use each. Specs
and code name tokens, never raw hex or raw pixels.

It uses the token shape of the Design System Artifact type, so the same file
feeds the canvas's Theme menu and could seed a published design system later.

## Shape

```json
{
  "name": "Orders",
  "version": 1,
  "color": {
    "themes": [{"id": "light", "name": "Light"}, {"id": "dark", "name": "Dark"}],
    "tokens": [
      {"name": "surface", "value": {"light": "#ffffff", "dark": "#111827"}, "usage": "Root background of a screen."},
      {"name": "on-surface", "value": {"light": "#0f172a", "dark": "#e5e7eb"}, "usage": "Primary text on surface."},
      {"name": "primary", "value": {"light": "#2563eb", "dark": "#3b82f6"}, "usage": "Primary actions and links."}
    ]
  },
  "type": {
    "fonts": [{"family": "Acme Sans", "file": "fonts/AcmeSans-Regular.woff2", "weight": "400"}],
    "families": {"sans": "\"Acme Sans\", system-ui, sans-serif"},
    "groups": [
      {"name": "Text", "family": "sans", "styles": [
        {"name": "body", "fontSize": "16px", "lineHeight": "24px", "fontWeight": 400},
        {"name": "heading-1", "fontSize": "24px", "lineHeight": "32px", "fontWeight": 700}
      ]}
    ]
  },
  "spacing": {"tokens": [{"name": "space-md", "value": "16px", "usage": "Default padding."}]},
  "radius": {"tokens": [{"name": "radius-md", "value": "8px", "usage": "Buttons, cards."}]},
  "shadow": {"tokens": [{"name": "e1", "value": "0 1px 2px rgba(0,0,0,0.08)", "usage": "Resting card."}]}
}
```

Rules the canvas enforces (a token that breaks one is dropped silently):

- Every family except `type` is `{"tokens": [{"name", "value", "usage"}, …]}`,
  a list. A name-to-value map (the W3C/DTCG `$value` format) reads as empty:
  convert it to lists.
- Names match `[A-Za-z0-9][A-Za-z0-9_.-]{0,63}` (no spaces, no `/`) and are
  unique across every family except `type`.
- Colors are hex, `rgb()`/`rgba()`/`hsl()`/`oklch()` with no function inside,
  or an alias `"{other-token}"` of an existing color token. No named colors
  (`red`, `transparent`, `currentColor`), no `var()`, no `color-mix()`.
- A plain string value is the first theme's; a theme a token omits inherits
  the first theme's value, so the primary theme goes first. No dark mode:
  one theme.
- Lengths are `px`, `rem`, `em`, `%` or a number; `lineHeight` may be
  unitless; `fontWeight` is a number or a range like `"300 800"`.
- A hosted (Google) font has no `file`: name it in `families` only.
- Every token has a `usage`: it is the when-to-use rule a spec and a reviewer
  read.

A value nobody has decided stays out of the file and is listed as `TBD` in the
`docs/design/README.md` overview instead: a seeded value that looks official gets
built against.

## Wiring it into the code

The code reads the same names through the mechanism the project already uses:
CSS custom properties (`--primary`, `--space-md`), the Tailwind theme, or the
framework's theme file (SwiftUI, Compose, iced, egui…). Generate or edit that
file so every token in `tokens.json` exists there under its name; a token used
in code but missing from `tokens.json` goes into `tokens.json` first.

## Installing it into the canvas

The canvas writes values inline in its artboards, as the Design type expects,
taken only from `tokens.json`: every color, size and radius on an artboard is
one token's value, so a reader maps it back by value. When a token changes,
change it in `tokens.json` and then in every artboard that uses its old value.

Installing the file as the canvas's design system (`project/ds/<folder>/tokens.json`
plus a `designSystems` record in `canvas.json`) is accepted by the server with
no Design System artifact behind it (tested), but whether the canvas then
offers those tokens in its editor was not confirmed. Do not rely on it.
