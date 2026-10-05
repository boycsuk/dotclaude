<!--
  No frontmatter / no paths: — this rule is always-on (same priority as
  CLAUDE.md), and non-fork subagents load it too. Workflow conventions
  (branching, commits, CHANGELOG, verification) are not tied to a file type,
  so they cannot be path-scoped: a commit or a branch is not a file Claude
  reads. The hooks named below deliver their own deny messages and opt-outs
  (allowPushToMain, allowCommitTrailers), so those details are not restated.
-->

# Workflow

## Branching
One branch per feature/fix (`feature/<name>`, `fix/<name>`); merge to `main` only when complete and verified. The `guard-push-main` hook protects main and blocks force pushes; branch naming and merge discipline are on you. Feature branches stay local: `/commit` offers to merge into main (`--no-ff`) and push main, never the branch.

## Atomic, descriptive commits
One logical change per commit; the message covers what and why. Prefer a new commit over `--amend`. English, plain-text messages, no attribution trailers — the `guard-commit` hook enforces this.

## Work in small chunks
One function, one bug, one feature at a time.

## Done means verified, with evidence
Verify as you go: errors compound in long sessions. A task is done only when it compiles, passes its tests (if any) and is logged in `CHANGELOG.md` — `/verify`, then `/commit` (it handles the CHANGELOG). When you claim done, show the evidence: quote the command that proves it and its result, or the `/verify` report; never "should work". A subagent's "success" is not verification.

## Understand before implementing
Ask when requirements are ambiguous; never write code on a guess. For a non-trivial feature (more than ~3 files, ambiguous requirements, or an architectural decision) use `/plan-feature`.

## Read sibling files before generating code
Before writing new code in an area, read 2-3 sibling files and match their conventions (escape clause for harmful patterns: `rules/code-quality.md`).

## Challenge assumptions
If something is unclear or suboptimal, say so and offer alternatives: flag tradeoffs, name risks, propose better options. **Never agree just to be agreeable** — back corrections with official documentation first, then community experience. Sycophancy is a failure mode; honest disagreement is the contract.
