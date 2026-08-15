---
name: changes
description: Summarizes the current uncommitted changes (staged + unstaged + untracked) in the working tree and flags risks in them. Use before requesting a review or opening a PR, or to take stock of work-in-progress edits. For rebuilding project context at the start of a session (CLAUDE.md, CHANGELOG, recent commits), use resume-context instead.
model: haiku
context: fork
background: false
allowed-tools: Bash(git status:*) Bash(git diff:*) Read
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

## Your task

Summarize in four short sections, one or two lines each:
- **What changed**: group by area of the codebase, not file by file.
- **Probable intent**: infer the purpose from the modifications.
- **Risks**: unhandled edge cases, missing tests, hardcoding, likely regressions.
- **Relevant untracked files**: ignore build artifacts, caches, dependency directories. Untracked files appear by NAME only above — if a small untracked source file looks central to the change, `Read` it before summarizing; otherwise name it and say its content was not reviewed.

If there are no changes at all (empty diff and no untracked files), say so. Do not invent changes.
