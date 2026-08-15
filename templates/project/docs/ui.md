# UI

> **What this file is.** The visual + navigational contract of the product:
> the brand design tokens (colors, typography, spacing, radii) every client
> shares, and the list of top-level sections/screens the user can reach. It
> is platform-agnostic — web, iOS, Android and desktop all implement the same
> product, so they share these names and values. How each client expresses a
> token (CSS variable, SwiftUI `Color`, Compose `Color`, Tailwind config) is
> implementation detail and stays in that client's source.
>
> **What this file is NOT.** Not component docs (buttons, inputs, cards live
> in source), not per-section endpoint wiring (that is backend's contract,
> in `backend.md`), not behavior (what the user can DO lives in
> `user-stories.md`). This file answers "what does it look like and what
> screens exist", nothing more.
>
> **How to keep it true (no tooling required).** This is a plain Markdown
> file — maintain it by hand in any editor. With Claude Code you can run
> `/update-docs` to do it from the diff; without it (Xcode, a sandboxed
> editor, a teammate), just edit it directly. Update it whenever a section is
> added/removed/renamed or its purpose changes, or whenever a design token is
> added/removed or its value changes. **Coverage over depth:** every section
> and every token must appear, even as a one-liner; a partial list that looks
> complete is worse than no list. If a token has no agreed value yet, leave it
> `TBD` rather than omit the row.

## Overview

<!-- One short paragraph: what the product looks like at a glance, which
clients implement it (web / iOS / Android / desktop), light/dark support.
Example: "Consumer app implemented as a SwiftUI iOS client and a Next.js web
client sharing the tokens below. Light and dark mode supported." -->

## Sections

<!-- One bullet per top-level area the user can navigate to, with a one-line
purpose. Just the map of screens — NOT what the user does in detail (that is
user-stories.md) and NOT which endpoints they call (that is backend.md).

Platform parity is the default: list a section once. Only annotate a platform
when the section genuinely exists on some clients and not others, e.g.
"Admin panel — web only". Remove this placeholder once real sections exist.

- **Login** — sign in / sign up.
- **Home** — landing screen after auth; recent activity.
- **History** — full, filterable list of past activity.
- **Settings** — profile, preferences, sign out.
- **Admin panel** — manage users and content. *(web only)*
-->

## Design tokens

<!-- The cross-client visual contract: NAMES + VALUES + when-to-use. Every
client MUST use these names, never raw hex / raw pixels. Do not document
components here. If the project has no dark mode, drop the Dark column and say
so.

EVERYTHING BELOW IS A PLACEHOLDER — invented values, not this project's design.
Replace each one with the real token before treating this file as a contract,
then delete this comment so the tokens become live. Left inside a comment on
purpose: a seeded palette that LOOKS official is worse than an empty section,
because clients build against it and the design system inherits colours nobody
chose.

### Brand colors

Semantic names (use these in code, never raw hex):

| Token           | Light     | Dark      | Use                                     |
|-----------------|-----------|-----------|-----------------------------------------|
| `primary`       | `#2563EB` | `#3B82F6` | Primary actions, links, brand accents.  |
| `on-primary`    | `#FFFFFF` | `#FFFFFF` | Content on a `primary` surface.         |
| `secondary`     | `#7C3AED` | `#A78BFA` | Secondary actions, less-emphasized.     |
| `success`       | `#16A34A` | `#22C55E` | Positive feedback, confirmations.       |
| `warning`       | `#D97706` | `#F59E0B` | Non-blocking warnings.                   |
| `danger`        | `#DC2626` | `#EF4444` | Destructive actions, validation errors. |
| `background`    | `#FFFFFF` | `#0B1220` | Root background of a screen.            |
| `surface`       | `#F8FAFC` | `#111827` | Elevated containers (cards, sheets).    |
| `on-background` | `#0F172A` | `#E5E7EB` | Primary text on `background`.           |
| `on-surface`    | `#0F172A` | `#E5E7EB` | Primary text on `surface`.              |
| `muted`         | `#64748B` | `#94A3B8` | Secondary text, helper labels.          |
| `border`        | `#E2E8F0` | `#1F2937` | Dividers, input borders.                |

### Typography

| Token         | Size | Weight | Use                              |
|---------------|------|--------|----------------------------------|
| `display`     | 32px | 700    | Hero / landing titles.           |
| `heading-1`   | 24px | 700    | Page titles.                     |
| `heading-2`   | 20px | 600    | Section titles.                  |
| `heading-3`   | 16px | 600    | Subsection titles.               |
| `body`        | 16px | 400    | Default text.                    |
| `body-strong` | 16px | 600    | Emphasized inline text.          |
| `caption`     | 13px | 400    | Labels, helper text, timestamps. |

Font family: `<system-ui / Inter / SF Pro / Roboto / …>` — fill in once
decided. Line-height: `1.5` body, `1.2` headings (override only with reason).

### Spacing scale

Base unit `4px`. Use multiples of the base; never raw pixels in code.

| Token | px | Typical use                               |
|-------|----|-------------------------------------------|
| `xs`  | 4  | Icon-text gap, tight chip padding.        |
| `sm`  | 8  | Inline gap, compact form padding.         |
| `md`  | 16 | Default vertical/horizontal padding.      |
| `lg`  | 24 | Section padding, modal padding.           |
| `xl`  | 32 | Page-level padding, big gaps.             |
| `xxl` | 48 | Hero spacing, top-of-page breathing room. |

### Radii

| Token         | px | Use                             |
|---------------|----|---------------------------------|
| `radius-sm`   | 4  | Inputs, chips.                  |
| `radius-md`   | 8  | Buttons, cards.                 |
| `radius-lg`   | 16 | Sheets, modals.                 |
| `radius-full` | ∞  | Circular avatars, pill buttons. |

### Elevation (optional)

Only if the platforms support shadows / surface elevation. Document the
**levels** here; concrete shadow values are platform-specific and stay in
each client's source.

| Token | Use                                       |
|-------|-------------------------------------------|
| `e0`  | Flat. No shadow.                          |
| `e1`  | Resting card. Light shadow.               |
| `e2`  | Hover / focus card. Medium shadow.        |
| `e3`  | Modal, popover, top sheet. Strong shadow. |

End of the placeholder block — replace the values above with this project's
real tokens and delete the `<!--` opener under "## Design tokens" plus this
closing marker so they become the live contract.
-->

Do not invent values — agree them with design before committing.
