<!--
  No frontmatter / no paths: — this rule is always-on (same priority as
  CLAUDE.md). Workflow conventions (branching, commits, CHANGELOG, verification)
  are not tied to a file type, so they cannot be path-scoped: a commit or a
  branch is not a file Claude reads.
-->

# Workflow

## Branching
One branch per feature/fix (`feature/<name>`, `fix/<name>`); merge to `main` only when complete and verified. The main-protection half is enforced deterministically by the `guard-push-main` hook (blocks direct pushes to main/master and all force pushes); branch naming and merge discipline are advisory — on you. Opt out of the main-block for solo/scratch repos via `"allowPushToMain": true` in `.claude/settings.local.json`; force push stays blocked regardless. Feature branches stay local: once the work is done, `/commit` offers to merge the branch into main (`--no-ff`) and push main, never the branch.

## Atomic, descriptive commits
- One logical change per commit.
- Message covers both what and why.
- Prefer a new commit over `--amend`. English, plain-text messages; no attribution trailers. The `guard-commit` hook enforces this (denies trailers, emoji and Spanish messages; asks before `--amend`, commits on main and commits without the CHANGELOG entry), and `attribution` in the central settings disables Claude's own byline. A project that requires `Signed-off-by` opts out with `"allowCommitTrailers": true` in `.claude/settings.local.json`.

## Work in small chunks
One function, one bug, one feature at a time. Avoid large monolithic requests.

## Incremental verification
Review and validate before moving forward — in long sessions errors accumulate if not caught early. A task is done only when it compiles, passes tests (if any), and is logged in `CHANGELOG.md`. Use `/verify` to validate behavior and `/commit` to commit (it handles the CHANGELOG in Keep a Changelog 1.1.0 + SemVer format); don't restate their mechanics here.

## Understand before implementing
Analyze context and ask questions before generating code. Never write code without explicit confirmation when the requirements are ambiguous. For non-trivial features (more than ~3 files, ambiguous requirements, or an architectural decision), use `/plan-feature` — it structures this interview and produces a SPEC.md; don't restate its mechanics here.

## Read sibling files before generating code
Before writing new code in an area, read 2-3 sibling files and match their conventions. Full guidance (and the escape clause for genuinely harmful patterns) lives in `rules/code-quality.md` → "Match existing conventions before inventing new ones".

## Challenge assumptions
If something is unclear or suboptimal, say so directly and offer alternatives. Do not accept a request just because it was asked — flag tradeoffs, name risks, and propose better options when they exist.

**Never agree just to be agreeable.** If the user is confused or heading in a suboptimal direction, say so. Back up corrections with official documentation first, then cross-reference with community experience, and present a balanced answer with options. Sycophancy is failure mode — honest disagreement is the contract.
