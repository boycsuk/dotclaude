---
name: commit
description: Creates a verified, convention-following git commit (the full procedure is in the body). Use when the user invokes /commit, asks to commit, or has verified, uncommitted work that is a natural commit point — but NEVER run the actual commit without explicit user confirmation (see the gate in the body). Proposing to commit is proactive; committing is not.
allowed-tools: Bash(git status:*) Bash(git diff:*) Bash(git add:*) Bash(git log:*) Bash(git commit:*) Bash(git branch:*) Read Edit
---

# Commit

Workflow to commit the current changes.

> **Hard gate — applies however this skill was triggered (user `/commit` OR
> model auto-invocation).** The `git commit` command runs ONLY after the user
> explicitly confirms the proposed message **in their reply to that proposal**
> (their next message after it) — "ok", "commit", "yes", or the Commit option
> of the confirmation question. A confirmation given *before* the message was
> proposed does not count. If this skill was auto-invoked because the work
> looked done, you may walk steps 1–5 and *propose* the commit, but you must
> STOP at step 6 and wait — never commit on your own initiative. When in
> doubt, do not commit.
>
> Note: the `Bash(git commit:*)` grant above covers the invocation turn only;
> it has expired by the time the user confirms, so the actual commit runs
> under the session's normal Bash permission (central settings, DESIGN.md §9).

## 1. Current state

```!
git status
git diff --stat
git log --oneline -5
```

## 2. Verify

Before committing, run the `/verify` skill (it owns the tests + lint + typecheck chain and the stack detection — do not reimplement those commands here). If `/verify` reports a failure, **stop** — do not commit. If the user already ran `/verify` in this session and nothing changed since, you may skip re-running it and say so.

## 3. Show the full diff

```!
git diff
git diff --staged
```

Analyze what changed. If there are untracked files that look relevant, propose adding them **by name**. Never `git add -A` or `git add .` without listing the files first. Untracked files do not appear in any diff — `Read` each one you intend to propose (or at least its head) before proposing it, and flag anything that looks like a secret, a build artifact, or an accidental dump instead of adding it.

Also check the branch: if you are on `main`/`master` and `allowPushToMain` is not set in `.claude/settings.local.json`, say so now and offer (via `AskUserQuestion`) to create a `feature/<name>` / `fix/<name>` branch first — `guard-push-main` will block the push later anyway, so surfacing it here saves a rewrite.

## 4. Update CHANGELOG.md

If the project has no `CHANGELOG.md`, ask via `AskUserQuestion` whether to create one (Keep a Changelog 1.1.0 skeleton) or skip this step — never invent one silently. If it exists without an `## [Unreleased]` section, add one at the top; if it follows a different format, match that format instead.

**If this skill was auto-invoked** (the model decided, not the user), do NOT write the file yet: draft the entry and show it with the proposed message in step 6, then apply it after confirmation. When the user invoked `/commit`, edit the file now.

Add an entry under `## [Unreleased]` in the correct category:
- `Added` for new features.
- `Changed` for changes in existing functionality.
- `Deprecated` for soon-to-be removed features.
- `Removed` for now removed features.
- `Fixed` for bug fixes.
- `Security` for vulnerability fixes.

Format: Keep a Changelog 1.1.0 — one line per change, present tense, descriptive but concise. ISO 8601 dates only for released versions, not for the `[Unreleased]` section.

## 5. Propose the message

- Follow the repo's existing convention (look at `git log` recent messages).
- Default: `<type>: <imperative description>` where type is feat/fix/refactor/docs/test/chore.
- Subject line: one line, <72 characters, imperative.
- Add a short body (blank line, then 1–3 lines) whenever the **why** does not fit in the subject — `workflow.md` requires the message to cover what AND why.
- No automatic co-author or sign-off lines unless the user requests them.

## 6. Confirm and commit

Show the proposed message (and the CHANGELOG entry, if drafted in step 4) and confirm via `AskUserQuestion` with options like **Commit** / **Edit the message** / **Don't commit**. Only the Commit option — or an explicit typed "ok"/"commit"/"yes" in reply — authorizes the commit; silence, a topic change, or "looks good on the code" does not (see the hard gate at the top).

Once confirmed:
1. Re-run `git status` — the output injected at the top of this skill is from load time and is now stale (the CHANGELOG edit came after it).
2. `git add` the agreed files **by name**, always including the `CHANGELOG.md` you edited.
3. Then `git commit`.

## Forbidden

- Never use `--amend` without explicit user request.
- Never use `--no-verify`. If a pre-commit hook fails, fix the underlying cause.
- Never add `Co-Authored-By` or similar trailers automatically.
