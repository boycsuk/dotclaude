---
name: audit
description: Use for a security review before committing or merging, a whole-project audit, hunting dead or unused code or duplication, checking comments and tests, finding repeated markup that should be components, or asking how a feature could be improved or what it is missing. Two modes, defects and improvements, with the categories and the depth chosen by the user. For a quick bug-focused pass over the current diff use /code-review.
argument-hint: "[defects|improve] [categories…] [light|medium|deep] [uncommitted|branch|<path>]"
effort: high
allowed-tools: Bash(npm *) Bash(pnpm *) Bash(npx --no-install *) Bash(uv *) Bash(uvx --offline *) Bash(python3 *) Bash(pip *) Bash(cargo *) Bash(go *) Bash(staticcheck *) Bash(git *) Bash(rg *) Bash(grep *) Bash(find *) Bash(wc *) Bash(ls *) Bash(gitleaks *) Bash(trufflehog *) Bash(pip-audit *) Bash(govulncheck *) Glob Grep Read Agent WebSearch WebFetch
---

# Audit

One entry point for reviewing code, whether it was written five minutes ago or five months ago: for what is wrong with it, or for what would make it better. It replaces the old `/security-review`: security is now one selectable category here, and "uncommitted changes" one selectable scope, so a pre-commit security pass is `/audit` → Defects → Security → Light → Uncommitted changes (or `/audit defects security light uncommitted`).

`/code-review` remains separate and complementary: it is a fast, bug-focused pass over the current diff. Reach for `/audit` when you want to choose *what kind* of problem to look for, or to look at code that is not in the diff at all.

## Two modes: defects or improvements

- **Find defects** — what is wrong: vulnerabilities, dead code, duplication,
  comment and doc hygiene, test gaps, and on web projects duplicated styles
  and markup that wants to be a component. Read
  `references/defect-mode.md` and follow it.
- **Propose improvements** — what is missing from something that already
  works: new capabilities, better UX, headroom for scale, a cleaner
  component API. Read `references/improve-mode.md` and follow it.

§0 below applies to both. Take the mode from the request when it is clear
("audit for security", "how could this table be better"); otherwise ask it
first, through AskUserQuestion, before any other question. Read only the
reference for the chosen mode.

## Arguments

**Arguments given:** $ARGUMENTS

(Nothing after the colon means none were given: ask every question as the
mode's reference describes.)

Each word that **exactly** names one of these pre-answers that question, and
only the remaining questions are asked:

- **Mode**: `defects`, `improve`.
- **Categories** (defect mode): `security`, `dead-code`, `duplication`,
  `comments`, `tests`, `styles` (the last only on a web/UI project). Several
  may be given.
- **Depth**: `light`, `medium`, `deep` (`deep` exists only in defect mode;
  in improve mode say so and ask).
- **Scope** (defect mode): `uncommitted`, `branch` (the "This branch"
  scope), or a path, which is the "one directory" scope.
- **Target** (improve mode): the words that are not a mode or a depth name
  the target — a component, screen, module or feature.

Rules, in order:

- **Do not guess.** A word that is none of the above, or could be two of
  them (a `tests` directory and the Tests category; a path that does not
  exist), is not mapped: ask the question it might have answered, naming
  the word.
- **Depth is never inferred.** Only `light`, `medium` or `deep` set it.
  "Quick look", "thorough" or "before the release" do not: the same words
  mean different budgets on different weeks, and choosing that budget is
  the user's call (DESIGN.md §28). Ask it.
- **Medium and Deep still show their cost.** When the depth came from the
  arguments, size the job as the reference says and state the scope size
  and the agent count in one line before dispatching anything.
- The mode reference's other rules still apply to a pre-answered run: all
  categories selected still gets the cost warning and the offer to split.

## 0. Audit and fix are two phases, and only the first one is expensive

Read this before choosing a depth — it is the single most useful thing learned from running this at scale:

- **Auditing fans out. Fixing does not.** Parallel subagents are what make a broad audit possible, and they are also the entire cost: a wide fan-out can burn well over a million tokens in one go. Applying the findings afterwards, in the main thread, one file at a time, is comparatively free.
- **So: audit once, wide. Then apply in series.** Never re-run the fan-out to "check your work" after fixing — verify with the deterministic tools and the project's own tests instead.
- **Budget in units of agents, not of ambition.** Roughly one agent per unit of work; a hundred-agent audit is a hundred agents' worth of tokens whether or not the findings are worth it.

## Route

- **Defects** → read `references/defect-mode.md` and follow it (§1-§5).
- **Improvements** → read `references/improve-mode.md` and follow it (§1-§6).
