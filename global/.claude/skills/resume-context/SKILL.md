---
name: resume-context
description: Rebuilds project context at the start of a session by reading CLAUDE.md, recent CHANGELOG entries, and git log. Use when opening a new session on an ongoing project or returning after a break. For summarizing the current uncommitted diff specifically, use changes instead.
model: haiku
allowed-tools: Bash(git log:*) Bash(git status:*) Read
---

# Resume Context

## 1. Read project state

First, the git state (these commands are identical on Unix and Windows):

```!
git log --oneline -10
```

```!
git status
```

Then read the project docs with the **Read tool** (not shell `cat`/`head`/`test` — those are not portable to Windows and trip the permission matcher):
- Read `CLAUDE.md` if it exists.
- Read the first ~50 lines of `CHANGELOG.md` if it exists.

A missing file just returns an error from Read — skip it and move on; do not treat it as fatal.

Rules load themselves — the central ones in `~/.claude/rules/` (always-on ones are already in context; `paths:`-scoped ones attach when you read a matching file) and any the project adds in `.claude/rules/`. Do not go looking for them.

## 2. Summarize for the user

Return a summary in four blocks:

- **Current state**: branch, recent commits, files not committed.
- **Recent relevant changes**: from the CHANGELOG `[Unreleased]` section and the latest released entries.
- **Active architectural decisions**: from CLAUDE.md — the `WHY` section in template-derived projects, or whatever section documents decisions and constraints otherwise. Omit this block only if CLAUDE.md has neither.
- **Work apparently in progress**: inferred from `git status` + last commit message.

If auto-memory notes appear in your context, weave the relevant ones into the summary — do not go looking for them on disk.

Keep the summary scannable: bullets, no prose paragraphs.
