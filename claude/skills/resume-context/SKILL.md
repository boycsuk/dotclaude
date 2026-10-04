---
name: resume-context
description: Rebuilds project context at the start of a session by reading CLAUDE.md, recent CHANGELOG entries, git log, and any work in flight (a SPEC.md, unfinished design units, unmerged branches). Use when opening a new session on an ongoing project or returning after a break. For summarizing the current uncommitted diff specifically, use changes instead.
model: haiku
context: fork
background: false
allowed-tools: Bash(git log:*) Bash(git status:*) Bash(git branch:*) Read Glob
---

# Resume Context

## 1. Read project state

First, the working tree (identical on Unix and Windows):

```!
git status
```

Then run `git log --oneline -10` with the **Bash tool**. In a repo with no commits yet it fails (exit 128): that is not an error, just report "no commits yet". It is deliberately not injected above — a failing injected command aborts the whole skill.

Then read the project docs with the **Read tool** (not shell `cat`/`head`/`test` — those are not portable to Windows and trip the permission matcher):
- Read `CLAUDE.md` if it exists.
- Read the first ~50 lines of `CHANGELOG.md` if it exists.

A missing file just returns an error from Read — skip it and move on; do not treat it as fatal.

Rules load themselves — the central ones in `~/.claude/rules/` (always-on ones are already in context; `paths:`-scoped ones attach when you read a matching file) and any the project adds in `.claude/rules/`. Do not go looking for them.

## 2. Look for work in flight

Each of these is optional; skip silently whatever is absent.

- **Specs**: Glob `SPEC*.md` at the project root (written by `/plan-feature`, meant to be implemented in a later session). For each, Read only its "Steps in order" and "Open questions" sections.
- **Design units**: if `docs/design/README.md` exists, Read only its component and screen status tables and list the rows whose status is not `verified`.
- **Unmerged branches**: run `git branch --no-merged main` with the Bash tool; if `main` does not exist, `git branch --no-merged master`. If neither exists, skip this.

## 3. Summarize for the user

Return a summary in four blocks:

- **Current state**: branch, recent commits (or "no commits yet"), files not committed.
- **Recent relevant changes**: from the CHANGELOG `[Unreleased]` section and the latest released entries.
- **Active architectural decisions**: from CLAUDE.md — the `WHY` section in template-derived projects, or whatever section documents decisions and constraints otherwise. Omit this block only if CLAUDE.md has neither.
- **Work apparently in progress**: inferred from `git status` + last commit message, plus step 2: each spec with its next step and open questions, design units not yet `verified`, unmerged branches. One line each.

If auto-memory notes appear in your context, weave the relevant ones into the summary — do not go looking for them on disk.

Keep the summary scannable: bullets, no prose paragraphs.
