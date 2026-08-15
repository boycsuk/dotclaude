---
name: audit
description: Audits code for vulnerabilities, dead code, duplication, comment/doc hygiene, test coverage, and (on web projects) duplicated styles and repeated markup that should be components. Asks WHICH categories, then how deep, then over what — nothing runs before those answers. Covers both uncommitted changes and code already in the repo. Use for a security review before committing, a whole-project audit, hunting dead or unused code or duplication, or checking what could become a component. For a quick bug-focused pass over the current diff use /code-review.
effort: high
allowed-tools: Bash(npx *) Bash(npm *) Bash(pnpm *) Bash(bunx *) Bash(uv *) Bash(python3 *) Bash(pip *) Bash(cargo *) Bash(go *) Bash(git *) Bash(rg *) Bash(grep *) Bash(find *) Bash(wc *) Bash(ls *) Bash(gitleaks *) Bash(pip-audit *) Bash(govulncheck *) Glob Grep Read Task
---

# Audit

One entry point for reviewing code quality and safety, whether the code was written five minutes ago or five months ago. It replaces the old `/security-review`: security is now one selectable category here, and "uncommitted changes" one selectable scope, so a pre-commit security pass is `/audit` → Security → Light → Uncommitted changes.

`/code-review` remains separate and complementary: it is a fast, bug-focused pass over the current diff. Reach for `/audit` when you want to choose *what kind* of problem to look for, or to look at code that is not in the diff at all.

## 0. Audit and fix are two phases, and only the first one is expensive

Read this before choosing a depth — it is the single most useful thing learned from running this at scale:

- **Auditing fans out. Fixing does not.** Parallel subagents are what make a broad audit possible, and they are also the entire cost: a wide fan-out can burn well over a million tokens in one go. Applying the findings afterwards, in the main thread, one file at a time, is comparatively free.
- **So: audit once, wide. Then apply in series.** Never re-run the fan-out to "check your work" after fixing — verify with the deterministic tools and the project's own tests instead.
- **Budget in units of agents, not of ambition.** Roughly one agent per unit of work; a hundred-agent audit is a hundred agents' worth of tokens whether or not the findings are worth it.

## 1. Ask in TWO rounds — nothing runs before both are answered

The categories come first and on their own, because auditing everything at once is exactly what makes an audit expensive and its report unreadable. One focused category answered well beats six answered shallowly.

### Round 1 — which categories? (`AskUserQuestion`, `multiSelect: true`)

- **Security** — vulnerabilities, hardcoded secrets, injection, missing authorization, unsafe deserialization. (Replaces the old `/security-review`.)
- **Dead code** — unreferenced exports, orphaned files, unused dependencies, unreachable branches, endpoints nobody calls.
- **Duplication & improvements** — copy-pasted logic, near-duplicate functions, N+1 queries, deep nesting, swallowed errors.
- **Comments & documentation** — comments that restate the code or narrate a past change, stale comments the code has outgrown, public APIs with no doc comment. Checks the project against `rules/code-quality.md`.
- **Tests** — risky logic with no test, suites that only cover the happy path, and tests that exercise a different entry point than production does (see §4 — that divergence is often the most valuable finding in the whole run).
- **Styles & components** *(web/UI projects only — omit this option entirely otherwise)* — repeated declaration blocks, hardcoded colours/spacing that should be tokens, dead selectors, and markup repeated 3+ times that wants to be a component.

If the user picks everything, say what that costs before proceeding (round 2 will quantify it) and offer to split it into two runs — the results are easier to act on that way.

### Round 2 — how deep, and over what? (one `AskUserQuestion` with both questions)

Before asking, **size the job**: count the files in scope (`git ls-files <scope> | wc -l`) so the options carry a real estimate instead of an adjective. State the expected agent count per option — "~1 agent per selected category (3 here)" means something; "costs more tokens" does not.

**Question 1 — depth:**
- **Light** — one pass in this context, driven by the deterministic tools. Minutes, no subagents. Good for a regular hygiene check, for a single category, and the right default on a repo audited recently.
- **Medium (recommended)** — one subagent per selected category, each with its own context, then a synthesis. **~1 agent per category selected in round 1.** The cost/benefit sweet spot for a project you have not audited before.
- **Deep** — fan out per module for each selected category, then adversarially verify each finding before reporting it. **Name the number** ("that is ≈N agents here") so the user is choosing a cost, not a word.

**Question 2 — scope:**
- **Uncommitted changes** — the working tree (staged + unstaged + untracked). The pre-commit pass; pairs naturally with Light.
- **Whole repo** / **one directory** (ask which) / **frontend only** / **backend only** — code at rest. Default to the whole repo when the project is small.

**On a large scope, prefer two Medium passes over one Deep pass.** Audit the riskiest half, apply the findings, then audit the rest — the second pass is smaller because the first one already taught you the codebase's failure patterns, and neither pass risks losing everything to one interruption.

### Scope determines what you read

- **Uncommitted changes:** `git status --porcelain`, `git diff --cached`, `git diff`. (Not `git diff HEAD` — it exits 128 in a repo with no commits and aborts the run.) Untracked files appear by NAME only and their content is in no diff: `Read` every untracked source file before judging it. A brand-new file with a hardcoded key is the single most valuable thing this scope catches, and reporting "nothing found" without having opened it is a silent false negative.
- **Code at rest:** the deterministic detectors below plus the per-category investigation.

## 2. Run the deterministic detectors first — at every depth

A linter that resolves imports beats an LLM guessing about reachability, and it is nearly free. **Run only the detectors belonging to a selected category** — a dead-code sweep on a security-only run is wasted time. Skip silently if the tool is absent (do NOT install anything without asking).

| Stack | Dead code / unused deps | Duplication |
|---|---|---|
| Node / TS | `npx knip` (best single tool: unused files, exports, deps) — else `npx ts-prune` + `npx depcheck` | `npx jscpd <scope>` |
| Python | `uvx vulture <scope>` or `python3 -m vulture <scope>`; `uvx deptry .` for deps | `npx jscpd <scope>` |
| Rust | `cargo +nightly udeps` if available; `cargo clippy -- -W dead_code` | `npx jscpd <scope>` |
| Go | `go vet ./...`; `staticcheck ./...` if available | `npx jscpd <scope>` |
| Any | `git grep -n "TODO\|FIXME\|XXX\|HACK"` for known debt | — |

Security scanners, when present: `npm audit --audit-level=moderate`, `pip-audit`, `cargo audit`, `govulncheck ./...`, plus `gitleaks detect` / `trufflehog` for historical secrets.

Record what you could NOT run and why — an audit that silently skipped half its tooling reads as a clean bill of health.

**Treat every tool result as a candidate, not a verdict.** Dead-code detectors have a well-known false-positive class: dynamic imports, reflection, framework entry points (route handlers, migrations, CLI plugins), re-exported public API, and anything referenced only from config or templates. Verify before reporting.

## 3. Investigate — only the categories selected in round 1

Ignore every category the user did not pick. Do not "throw in" a neighbouring dimension because it looked interesting: the point of round 1 is a report the user can act on, and an unrequested category dilutes it.

Scale the work to the chosen depth: at **Light** you do these passes yourself, sequentially; at **Medium** dispatch one subagent per selected category via `Task` and synthesize; at **Deep** fan out per module and then re-verify each surviving finding with a second, skeptical subagent whose job is to REFUTE it (drop what it refutes).

### Surviving an interrupted fan-out

A wide fan-out can hit a rate or usage limit partway through, and the agents that already finished are the expensive part — losing them means paying twice.

- **Persist findings as they arrive.** Append each agent's result to a scratch file (`<scratch>/audit-findings.json`) the moment it returns, rather than holding everything in context until the end. If the run dies, the completed work is on disk.
- **Make the units resumable and self-contained.** Give each agent a unit (a module, a dimension) that stands alone, so a re-run only needs to cover the units that failed — not the whole sweep.
- **On a limit, report what you have.** Say plainly which units completed and which did not, hand over the partial findings, and offer to finish the rest later. A partial audit stated as partial is useful; a partial audit presented as complete is a false clean bill of health.
- **Group the work; do not spawn one agent per file.** One agent per module or per dimension keeps the count in the single digits. Per-file fan-out multiplies cost without improving findings, because most findings are cross-file anyway.
- **Never re-run a completed unit.** If you must resume, resume — do not restart.

**Security.** Read `~/.claude/rules/security.md` first — it is the standard being audited against; if the project adds its own `.claude/rules/security.md` or a `docs/conventions.md` Security section, apply those too. Then work this checklist:

- [ ] Unvalidated input at a system boundary (request, file, env var).
- [ ] String concatenation building SQL, shell commands, or HTML.
- [ ] Missing resource-level authorization: an operation that trusts a client-supplied ID without checking the caller owns that record (IDOR), or an endpoint that is not deny-by-default.
- [ ] Server-side fetch of a user-supplied URL without a host/scheme allowlist (SSRF).
- [ ] Literal secrets in code (API keys, tokens, passwords).
- [ ] Token / hash comparisons using `==` instead of constant-time functions.
- [ ] Errors that expose stack traces, paths, or internal versions to the user.
- [ ] Deserialization of untrusted sources without validation.
- [ ] Permissions wider than strictly needed.
- [ ] Logs containing sensitive data.
- [ ] Security validations done only on the frontend.
- [ ] Custom cryptography (a red flag in almost every case).

**New dependencies** are part of this category: if the scope adds or bumps any, run the ecosystem audit (`npm audit --audit-level=moderate`, `pip-audit`, `cargo audit`, `govulncheck ./...`) and report what it finds even when non-critical — a moderate advisory in a new direct dependency is a decision the user should make knowingly.

**Dead code.** Unreferenced exports, unreachable branches, feature flags that are never false, commented-out blocks, orphaned files, dependencies nothing imports, endpoints no client calls, DB columns nothing reads. For each: state how you confirmed nothing references it, and say if the check was static-only.

**Improvements / duplication.** Copy-pasted logic that should be one function, near-duplicate functions differing by a constant, deep nesting that early returns would flatten, N+1 queries, sync I/O in hot paths, missing indexes, error handling that swallows failures.

**Comments & documentation.** Judge against `~/.claude/rules/code-quality.md`, which is the standard this project holds itself to — read it rather than inventing criteria.
- *Comments that should not exist*: paraphrases of the line below them; narration of a past change ("added X per request", "fixed the bug here"); decorative section banners; anything referencing a conversation instead of the code.
- *Comments that are now lies*: the most damaging kind. A comment describing behaviour the code no longer has actively misleads — worse than no comment. Check comments near recently-changed logic first.
- *Missing where it counts*: exported/public functions, classes and modules with no doc comment in the language's native format; and the reverse, doc comments that just restate names and types the signature already declares.
- Report a count plus the worst offenders, not every instance — "37 comments restate their code; here are the 6 worst" is actionable, a list of 37 is not.

**Tests.** Not "coverage is low" — coverage percentages are a weak signal. Look for:
- Risky logic with no test at all: auth checks, money/rounding, retries, concurrency, parsers, anything with a `TODO` near it.
- Suites that only walk the happy path: no test asserts the failure, the empty input, the timeout, the permission denial.
- **Tests that exercise a different entry point than production does** — see §4. A suite calling the inner function directly passes green while the wrapper, gate or config in front of it drops the input on the floor.
- Tests asserting implementation instead of behaviour (they break on every refactor and catch nothing).

**Machinery that never runs.** The highest-value findings are rarely broken code — they are code that *looks* fine and does nothing, because nothing exercises it. It attracts no bug reports precisely because it fails silently. Look for:
- A guard, hook, listener or validator whose output goes somewhere nobody reads (a log nobody tails, a channel the consumer ignores, a return value discarded by the caller).
- A gate in front of a parser: a prefix/regex pre-filter that is narrower than the thing it guards, so the careful logic behind it never sees the interesting input.
- A test whose fixtures bypass the production path — passing green while the real path is broken.
- A marker, flag or path a producer never emits: a check for `## foo` when the writer emits `### Foo` is a permanent false negative.
- A comparison whose semantics do not match the substrate: case-sensitive matching on a case-insensitive filesystem, byte sort on order-sensitive data.
- Documentation, config or scripts referencing paths that a refactor moved. These survive indefinitely because the strings stay plausible.

For each, the test is the same and it is not "does it look right": **can you point to evidence it actually fired?** If not, say so — "no evidence this ever runs" is a finding.

**Web (only for a web/UI project).**
- *Duplicated styles*: the same declaration block repeated across CSS/SCSS/styled-components/Tailwind class strings; hardcoded colors, spacing, and font sizes that should be design tokens; dead selectors matching nothing in the markup.
- *Repeated markup that should be a component*: the same element structure appearing 3+ times (cards, form fields, modals, empty states, badges). Report the concrete component boundary and the props it would take — not just "this repeats".

## 4. Report

Group by dimension, and inside each, order by severity. Every finding needs:
- `path:line` (clickable).
- **What** it is and **why** it matters, in one or two lines.
- The **fix** in a sentence — or a diff sketch when it is not obvious.
- **Confidence**: certain (verified) vs likely (static evidence only, e.g. a dead-code hit that could still be reached by reflection).

**A green test suite is not evidence a mechanism works.** Check that the tests exercise the same entry point production uses — a suite that calls the inner function directly passes happily while the wrapper, gate or config in front of it drops the input on the floor. When a test and the real path diverge, that divergence is itself the finding, and it is worth more than most of the report.

Close with:
- What was **not** covered: dimensions skipped, tools missing, directories out of scope.
- A short **suggested order of attack** — what to fix first for the best safety-to-effort ratio.

Do not inflate the report. A short list of real problems is worth more than fifty stylistic nits; if a dimension came back clean, say so in one line and move on.

## 5. Offer next steps

Fixing is a separate decision from finding. Offer via `AskUserQuestion`: fix the critical findings now / write them to a file for later / just leave the report. Never start refactoring off the back of an audit without asking — an audit touches code the user did not ask you to change.

If the user opts to fix, **apply in series, in this thread** — no fan-out (see §0). Work in small committed chunks grouped by concern rather than one giant change, verify each chunk with the project's own tests and linters, and keep the findings file open as the worklist so an interruption costs one chunk, not the session. Reproduce a bug before fixing it and pin it with a test where the project has one: several findings in any audit look real and are not.
