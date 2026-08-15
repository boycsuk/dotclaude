# Project documentation

This folder holds **portable contract docs**: a concise description of what
the system does and exposes, split across three files. It is meant to travel
with the repo so that anyone — a teammate, or any tool that can only see one
slice of the project (an Xcode workspace, an embedded subdir, a sandboxed
editor) — still has enough context to work coherently against the whole.

**These docs are plain Markdown and self-maintained.** With Claude Code you
run `/update-docs` to update them from the diff. Without it (a different IDE,
no skills, a teammate by hand) you just edit them directly — each file carries
its own maintenance rules in its header, so you never need this README or the
skill to keep it true. The skill is the convenience, not the requirement.

## The three files

- **`backend.md`** — the API contract. Every endpoint (path, method,
  request/response shape, status codes, auth), the shared error model, and
  cross-endpoint conventions. What a client can call and what comes back.
- **`ui.md`** — the visual + navigational contract. The brand design tokens
  (colors, typography, spacing, radii) every client shares, and the list of
  top-level sections/screens. What it looks like and what screens exist.
- **`user-stories.md`** — the behavioral contract. Everything the user must be
  able to DO, as platform-independent user stories. What the product can do
  for its user.

The three answer different questions and should not bleed into each other:
*what can a client call* (backend) vs *what does it look like* (ui) vs *what
can the user achieve* (user-stories). A capability shows up in `user-stories.md`
as an outcome, in `ui.md` as the screen it lives on, and in `backend.md` as the
endpoints behind it — same feature, three lenses, no duplication of detail.

Alongside the three product-contract files there is a fourth, different in
kind:

- **`conventions.md`** — *how to write the code* in this project (typing,
  error handling, security, git, output). The three above describe *what the
  system does*; this one describes *how contributors should build it*. It is
  the **repo-versioned copy** of the conventions: it travels with the clone and
  is what every contributor and non-Claude tool (Xcode, a sandboxed editor, a
  different assistant) actually reads. Developers using Claude Code also get the
  same conventions from their personal global rules (`~/.claude/rules/`), which
  are NOT checked in — so `conventions.md` is the one source present in a fresh
  clone, and must be kept in sync by hand when a convention changes.

Add more files (`cli.md`, `bot.md`, `events.md`, …) only when there is a *new
producer or consumer of contracts* another part of the system must understand
(e.g. a webhook feed, a CLI, a message bus). Do not create files just because
a folder exists.

## Platform model

Most products implement the same behavior on every client (web, iOS, Android,
desktop). So:

- `user-stories.md` and `ui.md` are **platform-agnostic by default**: write
  each story/section once.
- Only annotate a platform when a capability **genuinely differs** — e.g.
  *"Admin panel — web only"*, or a `Platform exception:` line under a story.
  Do not tag every entry with a platform matrix when almost all are identical;
  list the divergences, assume parity for the rest.
- Platform-specific *implementation* (SwiftUI views, React components, native
  share sheets) stays in each client's source, never here.

## Update discipline

These files are useful only if they are **true** and **complete**. Update them
**at the end of any task that changed a contract** — never speculatively,
never as scaffolding for work not yet done.

### Coverage over depth

**Every capability the system exposes must appear, even briefly.** A one-line
entry for every endpoint / section / story beats a perfect entry for some and
silence for the rest. The *what* must be exhaustive; the *how* and *why* can
stay shallow. When choosing between "skip it, it's not interesting" and "add a
one-liner so it exists", always pick the one-liner.

A change counts as a contract change when it adds, removes, or alters:
- a backend endpoint (path, method, request body, response shape, status
  codes, auth) → `backend.md`;
- a top-level section/screen, or a brand design token → `ui.md`;
- something the user can now do, can no longer do, or does differently
  → `user-stories.md`;
- any cross-component agreement another consumer relies on → the relevant
  file (or a new one).

A change does NOT count when it only touches:
- internal refactors, renamings of private helpers, logging, formatting;
- tests, build configuration, dependency bumps that do not change behavior;
- bug fixes that restore the documented behavior rather than change it.

When in doubt, ask: *"would a developer reading only `docs/` build the wrong
mental model after this change?"* If yes, update. If no, skip.

## Style

- English only (same rule as code and commit messages).
- Be concise. Bullets and tables beat paragraphs.
- No code dumps. Link to the source file if the reader needs more.
- No history or rationale here — that is what `CHANGELOG.md` and commit
  messages are for. These docs describe the system *as it is now*.
