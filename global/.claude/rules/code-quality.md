---
paths:
  - "**/*.{ts,tsx,js,jsx,mjs,cjs,py,pyi,rs,go,java,kt,kts,rb,php,c,h,cc,cpp,cxx,hpp,hh,cs,swift,scala,clj,ex,exs,erl,hs,ml,sql,vue,svelte,sh,bash,ps1,html}"
---
<!--
  Loaded when Claude reads a source file matching paths: above. There is no
  description: key — it is inert for rules (only Skills act on it). Caveat:
  path-scoped rules fire on Read, not on file *creation* — see
  anthropics/claude-code#23478. The "read 2-3 sibling files first" rule below
  mitigates this: reading a sibling pulls this rule in before you write.
-->

# Code Quality

## Match existing conventions before inventing new ones
Before writing new code in an area you have not touched this session, read 2-3 sibling files in the same module/folder and mimic their patterns: naming style, error handling, file structure, formatting, abstractions, import style, test layout. Treat them as the baseline unless explicitly asked to refactor. Consistency across the codebase is more valuable than locally-optimal "better" patterns — fragmenting the style fragments comprehension.

**Escape clause:** if the existing pattern is genuinely harmful (security flaw, broken type safety, an anti-pattern documented in this project's `Don't` section), do NOT replicate it. Surface the concern to the user and ask whether to refactor or to follow the existing style as-is for now.

## No speculative code
Only what is needed for the requested functionality. Nothing "just in case".

## Reusable code, zero hardcoding
- Literal values go to centralized configuration or named constants.
- Shared logic is abstracted, not duplicated.
- Each constant has a name that reveals intent.

## Strict typing
Type everything possible. Leverage the type system to prevent errors at compile time. Avoid `any`, `unwrap()`, `!.`, etc., in production paths.

## Explicit error handling
Every failed operation is logged or returned with enough context to diagnose. No silently swallowed errors.

## Structured logging
Levels (debug, info, warn, error) with structured context. Do not just log errors — log decisions, inputs to critical paths, and external call boundaries.

## Comments: default to none; earn each one
Comment the **why**, never the **what** — well-named identifiers describe the what. All comments in English.

- **Deletion test, applied before writing any comment:** if a competent reader gets the same information from the line plus its identifier names, the comment must not exist.
- **Comments that earn their place** (the only ones to write): a workaround with a link to the issue it dodges; a non-obvious invariant or constraint; a counterintuitive decision ("looks wrong but is correct because…"); a reference to a spec, RFC, or regulation; a warning about consequences of changing the code.
- **Never write:** comments that paraphrase the code; comments that narrate the session or the change ("added X per request", "fixed the bug here"); decorative section banners; comments that reference the conversation with the user.
- **Length:** one line by default. Multi-line only for genuinely complex invariants.
- **When editing code, delete comments the change makes obsolete** — don't edit around them.

## Document public functions with the language's native doc format
Doc comments are the deliberate exception to "never the what" — they are the API contract, not inline commentary.

- Every exported/public function, method, class, and module gets a doc comment in the language's native format: JSDoc, Python docstring (PEP 257), rustdoc `///`, godoc, Javadoc, C# XML docs, PHPDoc.
- Structure: one-line imperative summary; parameters and return value only when name + type don't already say it; errors/exceptions thrown; side effects.
- Do not duplicate what the type system already declares (TypeScript: no types in `@param`; typed Python: no types in the docstring) — consistent with "Strict typing" above.
- Private/internal helpers: document only if behavior is non-obvious; otherwise the name suffices.
- Follow the docstring style the project already uses (Google vs NumPy vs reST) — see "Match existing conventions".

## Do not delegate to the LLM what a linter does
Style (formatting, import order, naming) is enforced by the `verify-on-edit` hook running the project's linter. Do not waste the context window correcting it by hand.

## Tests with explicit intent
Do not just say "write tests". Specify the cases and expected behaviors before the AI writes the tests. Otherwise it produces tests for the happy path only.

## Verify external references
Only recommend libraries, functions, and APIs that verifiably exist and are currently maintained. If uncertain about a method signature or version, say so explicitly. Prefer well-known, actively maintained packages.

## Match logic to the real-world domain
Before choosing a data structure or algorithm, verify it maps correctly to the actual use case. A Queue (FIFO) for a support line, not a Stack (LIFO). If the requirement is ambiguous, ask — do not guess.

## Scalability awareness
State the time and space complexity of non-trivial algorithms. Watch for:
- O(n²) where O(n log n) is achievable.
- N+1 query problems.
- Missing indexes.
- Synchronous calls that should be async.

If a more scalable approach exists, mention it even if the requested approach is acceptable.

## Flat over nested ("no Hadouken Code")
Validate and reject invalid states at the top of a function with early returns. Keep the happy path flat. If a function has more than 2 levels of nesting, refactor it. Break complex functions into smaller, named sub-functions.

## No magic numbers or strings
- `86400` → `SECONDS_PER_DAY`.
- `"admin"` → a named constant.
- Every literal should have a name that reveals intent.

Exception: literals used only once in a clearly-named local context (e.g., `if status == 200`) can stay raw if the meaning is obvious from immediate context.
