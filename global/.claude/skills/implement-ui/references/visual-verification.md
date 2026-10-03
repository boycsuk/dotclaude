# Visual verification by target

The gate in step 5 needs two things per unit: an **image** of what the code
draws, at the size and in the state the spec describes, compared against the
reference (the artboard screenshot or the mockup); and the unit's
**acceptance checklist**, each line seen to hold on the running UI. How you
get them depends on the target. Take the first rung that applies, and say
which one you are on.

Acceptance lines are structural (a pager exists, a text reads X, Escape
moves focus there), so the toolkit's widget queries check them without
comparing pixels. Written as tests, they do not break across operating
systems the way image snapshots can; whether they stay in the repo follows
the project's convention, as for images.

If the project already renders its UI to an image somewhere (a test, a
script), that is its chosen pattern: reuse it before reaching for anything
below. Anything below that adds a dependency (a crate, a plugin, an MCP
server, a capture tool) is proposed to the user, never added silently.

## 1. Web

A Playwright-style browser MCP (a `playwright` entry in `.mcp.json`, deployed
by `init.sh --update --ui` in template projects): navigate to the dev server,
resize the viewport to the reference's size, screenshot, compare, fix,
re-screenshot. The structural check reads the page's accessibility snapshot.
No browser MCP: offer to add it (`claude mcp add playwright -- npx -y
@playwright/mcp@0.0.83`, a pinned version, never `@latest`, which re-resolves
on every start) and fall to rung 4 meanwhile.

The web frontend of a desktop shell (Tauri, Electron) is web for layout
purposes: run its dev server and use this rung, then check the real window
with rung 2 or 3.

## 2. Desktop toolkit that renders without a window

Most GUI toolkits can draw a screen to an image in a test, with no window and
no display. That beats any screenshot of a running app: the size is exact,
and you reach any state the spec shows by sending the app its own messages or
events, not by clicking coordinates.

The loop: build the app state the section needs, render it at the spec's
window size, write the image to a scratch path (delete the previous image
first, so you never look at a stale one), `Read` the PNG, compare, fix,
repeat. Use the toolkit's widget queries (find by text or label) for the
structural check.

Known facilities. For a toolkit not listed, look for its equivalent in its
docs before dropping to rung 3.

- **iced** (0.14+): `iced_test`. `Simulator::with_size(settings, size,
  view)` renders a view at a fixed size; drive the state through the app's
  `update(Message::…)` before building the view; `snapshot(&theme)` then
  `matches_image(path)` writes the PNG when the file does not exist and
  compares exactly when it does. `find` and `click` select widgets by text.
- **egui**: `egui_kittest` with the `snapshot` and `wgpu` features;
  `Harness::snapshot` writes under `tests/snapshots/`; `get_by_label` finds
  widgets through AccessKit.
- **Slint**: an embedded MCP server. Build with `--features slint/mcp`, run
  with `SLINT_EMIT_DEBUG_INFO=1` and `SLINT_MCP_PORT=<port>` (add
  `SLINT_BACKEND=headless` without a display); its tools take screenshots,
  read the UI tree and click, drag and type. Slint marks this entry point
  unstable.
- **Tauri**: rung 1 for the frontend; for the real window, the
  `tauri-plugin-mcp-bridge` plugin plus the `@hypothesi/tauri-mcp-server`
  MCP server (third party) give screenshots, DOM and input.
- **Flutter**: golden tests (`matchesGoldenFile`).
- **Qt**: `QWidget::grab()` to a pixmap, saved from a test.

The images are a tool for the loop. Whether they stay in the repo as tests
follows the project's existing convention; with none, ask before adding
permanent snapshot tests, and remember exact-match comparisons can fail
across operating systems because text renders differently.

## 3. Any desktop app: capture the running window

Pixels are toolkit-agnostic. Launch the app, capture its window with the
operating system's tool, whichever is installed (`screencapture` on macOS;
`import` from ImageMagick with `xdotool` on X11; `grim` on Wayland; a
PowerShell `System.Drawing` capture on Windows; or the cross-platform `xcap`
crate), and `Read` the PNG.

The limit: you see only the state the app is in. Reach other states through
whatever the app offers at launch (an argument, an environment variable, a
debug entry point); if it offers none, propose adding one, or cover those
states with rung 4.

Accessibility-tree automation (agent-desktop, WinPilot.Mcp and similar MCP
servers) can also click and read structure, but only in apps that expose an
accessibility tree. Many custom-drawn toolkits do not yet (iced, as of 0.14),
and there the window reads as one empty element.

## 4. Ask the user

Say which rungs were unavailable and why, and ask for a screenshot of the
running app at the spec's size. Keep going section by section with those.

## Comparing

List concrete differences: spacing, size, color, alignment, missing states,
text overflow. A native toolkit will not match an HTML artboard pixel for
pixel; the bar is the spec: same components, same placement, the same
tokens, and the same behaviour at the narrow size. Two or three iterations
is the normal convergence; do not stop at one.
