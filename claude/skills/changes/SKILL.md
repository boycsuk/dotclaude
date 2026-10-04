---
name: changes
description: Summarizes the current uncommitted changes (staged + unstaged + untracked) in the working tree, or a whole branch since main, and flags risks in them. Use before requesting a review or opening a PR, or to take stock of work-in-progress edits. For rebuilding project context at the start of a session (CLAUDE.md, CHANGELOG, recent commits), use resume-context instead.
model: haiku
context: fork
background: false
allowed-tools: Bash(git status:*) Bash(git diff:*) Bash(git branch:*) Bash(git merge-base:*) Bash(git log:*) Read
---

# Changes

> `context: fork` keeps the full diff (which can be large) out of the main conversation and scopes `model: haiku` to this summarizing run; the caller gets only the summary back, in the same turn.

## Current state

```!
git status
git diff --cached --stat
git diff --stat
```

## Full diff

Lockfiles are excluded here — they are noise at diff level and still show up in the `--stat` above.

```!
git diff --cached -- ':(exclude)package-lock.json' ':(exclude)pnpm-lock.yaml' ':(exclude)yarn.lock' ':(exclude)bun.lockb' ':(exclude)*.lock' ':(exclude)go.sum'
git diff -- ':(exclude)package-lock.json' ':(exclude)pnpm-lock.yaml' ':(exclude)yarn.lock' ':(exclude)bun.lockb' ':(exclude)*.lock' ':(exclude)go.sum'
```

> The pairs above are deliberate: `git diff HEAD` fails with exit 128 in a repo with no commits yet — and a failing injected command aborts the whole skill — while `--cached` + unstaged covers the same ground and works from the very first commit onwards.

## Scope

The default scope is the working tree above. When the request asks for the branch ("this branch", "before merging", "since main"), cover **this branch**: the commits since the branch left main, combined with whatever is still uncommitted above. At merge time all the work is already committed, so the working tree alone shows nothing.

Run these as ordinary Bash steps, one at a time — never as an injected block: any of them can fail (no `main`, HEAD on main itself, no commits yet), and a failing injected command aborts the whole skill.

1. `git branch --show-current` and `git branch --list main master`. The default branch is `main` if it exists, else `master`. If neither exists, or the current branch IS the default branch, say so in one line and summarize the working tree only.
2. `git merge-base <default> HEAD` gives `<base>`. If it fails, say so and fall back to the working tree.
3. `git log --oneline <base>..HEAD` and `git diff --stat <base>...HEAD`.
4. `git diff <base>...HEAD -- ':(exclude)package-lock.json' ':(exclude)pnpm-lock.yaml' ':(exclude)yarn.lock' ':(exclude)bun.lockb' ':(exclude)*.lock' ':(exclude)go.sum'`

Say which scope you covered: the working tree, or this branch from `<base>` plus the working tree.

## Your task

Summarize in four short sections, one or two lines each:
- **What changed**: group by area of the codebase, not file by file.
- **Probable intent**: infer the purpose from the modifications.
- **Risks**: unhandled edge cases, missing tests, hardcoding, likely regressions.
- **Relevant untracked files**: ignore build artifacts, caches, dependency directories. Untracked files appear by NAME only above — if a small untracked source file looks central to the change, `Read` it before summarizing; otherwise name it and say its content was not reviewed.

If there are no changes at all (empty diff, no untracked files and, on the branch scope, no commits since `<base>`), say so. Do not invent changes.
