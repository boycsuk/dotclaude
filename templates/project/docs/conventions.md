# Conventions

> **What this file is.** The coding conventions of this project, distilled so
> that any tool or contributor can follow them. If you are an AI or an editor
> working in this repo (Xcode, a sandboxed subdir, a different assistant),
> **read this file and follow it** before writing or changing code. This is the
> versioned, portable copy of the conventions — it travels with the repo and
> does not depend on any tool-specific config being present.
>
> **Relationship to Claude Code.** When the project is opened in Claude Code,
> the same conventions are also loaded from the user's global rules
> (`~/.claude/rules/`: `code-quality.md`, `security.md`, `workflow.md`,
> `ai-collaboration.md`) — those are personal to each developer's machine and
> are NOT checked into this repo, so a fresh clone will not contain them. This
> file is what every contributor and non-Claude tool actually reads. If a
> developer's global rules and this file ever diverge, reconcile them by hand
> (see the footer). A project may also add its own `.claude/rules/<topic>.md`;
> those are project-local additions, not a replacement for this file.
>
> **What this file is NOT.** Not the product contract — that is `backend.md`
> (API), `ui.md` (visual), and `user-stories.md` (behavior). This file is about
> *how to write the code*, not *what the code does*.

## Code quality

- **Match existing conventions first.** Before writing new code in an area,
  read 2-3 sibling files and mimic their naming, error handling, structure,
  imports, and test layout. Consistency beats locally-"better" patterns.
  Exception: do not replicate a genuinely harmful pattern (security flaw,
  broken type safety, a documented anti-pattern) — surface it instead.
- **No speculative code.** Only what the requested functionality needs. Nothing
  "just in case".
- **Strict typing.** Type everything the language allows; lean on the type
  system. Avoid `any`, `unwrap()`, `!.` and equivalents in production paths.
- **Explicit error handling.** Every failed operation is logged or returned
  with enough context to diagnose. No silently swallowed errors.
- **Structured logging.** Levels (debug/info/warn/error) with context. Log
  decisions and external-call boundaries, not just errors.
- **Reusable, zero hardcoding.** Literals go to named constants or central
  config; shared logic is abstracted, not duplicated. No magic numbers/strings
  (`86400` → `SECONDS_PER_DAY`, `"admin"` → a named constant). A literal used
  once in obvious local context (`if status == 200`) may stay raw.
- **Comments default to none; earn each one.** Only non-obvious whys deserve a
  comment: workarounds (with issue link), invariants, counterintuitive
  decisions, spec references, change warnings. One line by default. Never
  paraphrase the code, narrate the change ("added X per request"), or add
  decorative banners. Delete comments your edit makes obsolete. All comments in
  English.
- **Document public APIs in the language's native doc format** (JSDoc,
  docstring/PEP 257, rustdoc, godoc…) — the deliberate exception to "never the
  what". One-line imperative summary; params/return only when name + type don't
  already say it; errors and side effects always. Don't duplicate what the type
  system declares. Private helpers only if non-obvious.
- **Flat over nested.** Validate and early-return at the top; keep the happy
  path flat. More than ~2 levels of nesting → refactor into named helpers.
- **Tests with explicit intent.** Specify the cases and expected behavior, not
  just "write tests" — cover more than the happy path.
- **Verify external references.** Only use libraries/APIs that verifiably exist
  and are maintained. If unsure of a signature or version, say so.
- **Match logic to the domain.** Pick the data structure/algorithm that maps to
  the real use case (a FIFO queue for a waiting line, not a stack). Ask if the
  requirement is ambiguous.
- **Scalability awareness.** State the complexity of non-trivial algorithms;
  watch for O(n²) where O(n log n) is possible, N+1 queries, missing indexes,
  sync calls that should be async.
- **Don't hand-fix what a linter does.** Formatting, import order, and naming
  are the linter's job — run it, don't burn effort correcting style by hand.

## Security

> Review with at least the rigor of human-written code, especially anything touching I/O, auth, or deps.

- **Validate at every boundary.** All external input (user, API, file, env var)
  is validated and sanitized before use.
- **No injection.** Never build SQL, shell, or HTML by string concatenation —
  use parameterized queries, escape APIs, or safe templates.
- **Least privilege.** Each component gets only the access it needs.
- **Authorize every access, deny by default.** Verify server-side that the user
  may act on the *specific* resource (record ownership — IDOR); never trust
  client-supplied IDs. Validate server-fetched, user-derived URLs against an
  allowlist (SSRF).
- **Don't leak internals in errors.** User-facing errors stay generic; detail
  goes to server-side logs.
- **Constant-time comparison** for tokens/hashes/secrets (`hmac.compare_digest`,
  `crypto.timingSafeEqual`), never `==`.
- **No homegrown crypto.** Use established libraries.
- **Validate before deserializing** untrusted data; prefer data-only formats.
- **Secrets only in memory or a manager.** Never hardcode credentials, API
  keys, or tokens in source or committed config — load them from env vars or a
  secret manager. Never log, serialize, or put them in URLs. The repo blocks
  reads of `.env`/`secrets/`/`credentials/`.
- **Secure logs.** Never log sensitive data; sanitize inputs before logging
  (log injection via CRLF/escapes).
- **Limit resources.** Timeouts on external calls, input size limits, rate
  limiting where applicable.
- **TOCTOU.** If a check and its action must be inseparable, use atomic ops or
  locks.
- **Don't trust the client.** All security validation happens server-side;
  frontend checks are UX only.
- **Pin and audit dependencies.** Lockfiles + exact versions; run the
  ecosystem audit (`npm audit`, `pip-audit`, `cargo audit`, `govulncheck`).
- **Uploaded files:** validate by magic bytes, not extension; no execute bit on
  upload dirs.

## Workflow & git

- **One feature/fix per branch** (`feature/<name>`, `fix/<name>`); merge to
  `main` only when complete and verified. (In this repo a hook blocks direct
  pushes to main and all force pushes; other tools should follow the same
  discipline by hand.)
- **Atomic commits:** one logical change each; the message covers what and why.
  Never `--amend` without explicit confirmation. **Never add a
  `Co-Authored-By` / `Signed-off-by` trailer** unless explicitly requested.
- **Work in small chunks** — one function/bug/feature at a time.
- **A task is done** only when it compiles, passes tests (if any), and the
  change is recorded in `CHANGELOG.md` (Keep a Changelog 1.1.0 + SemVer).
- **Understand before implementing.** Ask when requirements are ambiguous;
  don't write code on a guess.
- **Keep the contract docs true.** If a change alters a contract, update the
  matching file in `docs/` (`backend.md` / `ui.md` / `user-stories.md`).

## Collaboration & output

- **Language:** talk to the user in their working language; keep everything
  *inside* the codebase in English (identifiers, comments, commit messages,
  logs, docs). Working language for this project: {{WORKING_LANGUAGE}}.
- **No emojis** in code, commits, messages, or docs unless strictly necessary.
- **Cite sources** (markdown links) when an answer relies on external docs or
  articles.
- **Plain-language explanations.** Lead with the outcome, then the detail;
  short sentences, everyday words; keep every fact, name, number, and file path
  exactly; no filler or meta-commentary; gloss unavoidable jargon on first use.
- **Ask for decisions with a multiple-choice prompt, not prose.** When you need
  the user to choose or decide, present 2-4 concrete options via the
  tool/UI for that (`AskUserQuestion` in Claude Code), not a typed-answer
  question. Plain prose only for genuinely open-ended input (a description, a
  name, a pasted error).
- **Challenge assumptions.** If something is unclear or suboptimal, say so and
  offer alternatives — back corrections with official docs first. Never agree
  just to be agreeable.
- **Fan out to investigate; apply in series.** Parallel agents are where the
  cost of an AI-assisted sweep goes; applying the findings one at a time in the
  main thread is comparatively free. Sweep once, group agents by module or
  dimension (never one per file), save results as they arrive so an
  interruption does not discard them, and verify fixes with the project's own
  tests rather than a second sweep.

---

*Maintenance: this is a hand-distilled, repo-versioned copy of the project's
conventions. When the team agrees a convention changes, update the matching
bullet here. For developers using Claude Code, mirror the change into their
global `~/.claude/rules/` too (and vice-versa); `/update-docs` and `/compound`
help flag drift, but the reconciliation is by hand since the global rules live
outside the repo. Keep it a concise summary — link to depth, do not paste
whole rules.*
