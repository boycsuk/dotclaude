---
name: commit
description: Creates a verified, convention-following git commit (the full procedure is in the body), and offers in the same confirmation to merge the branch into main and push main. Use when the user invokes /commit, asks to commit, or has verified, uncommitted work that is a natural commit point — but NEVER run the actual commit, merge or push without explicit user confirmation (see the gate in the body). Proposing to commit is proactive; committing is not.
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
> doubt, do not commit. The same gate covers step 7: the merge and the push
> run only when the option the user confirmed includes them.
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

Show the proposed message (and the CHANGELOG entry, if drafted in step 4) and confirm via `AskUserQuestion`. The options depend on the branch (`git branch --show-current`; the main branch is `main`, or `master` when there is no `main`) and on whether `.claude/settings.local.json` sets `"allowPushToMain": true`:

| On | Opt-out set | Options |
|---|---|---|
| a feature branch | yes | **Commit, merge into main and push** / **Commit only** / **Edit the message** / **Don't commit** |
| a feature branch | no | **Commit and merge into main** / **Commit only** / **Edit the message** / **Don't commit** — say that `guard-push-main` will block the push, so the user pushes main from their own terminal |
| main | yes | **Commit and push** / **Commit only** / **Edit the message** / **Don't commit** |
| main | no | **Commit** / **Edit the message** / **Don't commit** |

Recommend **Commit only** while the branch's work is unfinished; the merge is for when the feature is complete and verified (`workflow.md`). Only one of the commit options — or an explicit typed "ok"/"commit"/"yes" in reply, which means commit only — authorizes the commit; silence, a topic change, or "looks good on the code" does not (see the hard gate at the top).

Once confirmed:
1. Re-run `git status` — the output injected at the top of this skill is from load time and is now stale (the CHANGELOG edit came after it).
2. `git add` the agreed files **by name**, always including the `CHANGELOG.md` you edited.
3. Then `git commit`.
4. If the confirmed option includes a merge or a push, continue with step 7.

## 7. Merge into main and push

Feature branches stay local: never push one, never delete a remote branch. Stop at the first failure, report it with the command's output, and leave the repository as it is — no `reset`, `rebase` or `push --force` to get past it.

From a feature branch (`<branch>` below):
1. `git status --porcelain` must be empty; otherwise stop, because switching would carry the leftovers onto main.
2. `git switch main`, then `git pull --ff-only` when main has an upstream (`git rev-parse --abbrev-ref main@{upstream}` succeeds). If main and its remote have diverged, stop.
3. `git merge --no-ff <branch>`, keeping git's default `Merge branch '<branch>'` message. The merge commit keeps the branch's atomic commits and marks where the feature landed. On a conflict, list the files and ask via `AskUserQuestion`: **Resolve them together** / **Abort the merge** (`git merge --abort`). The usual one is the `[Unreleased]` section of CHANGELOG.md: keep both sides' entries.
4. If main had commits the branch did not (`git log --oneline <branch>..ORIG_HEAD` lists any), the merged result was never verified: run `/verify` now. If it fails, stop before pushing and say the merge is still local.
5. If the confirmed option includes the push: `git push` (`git push -u origin main` when main has no upstream). If it is rejected, report and stop; never force.
6. Ask via `AskUserQuestion` whether to delete the merged branch: **Delete `<branch>`** (`git branch -d <branch>`, which refuses a branch that is not fully merged) / **Keep it**.

From main (**Commit and push**): `git push` after the commit; if it is rejected because the remote moved, report and stop.

## Forbidden

- Never use `--amend` without explicit user request.
- Never use `--no-verify`. If a pre-commit hook fails, fix the underlying cause.
- Never add `Co-Authored-By` or similar trailers automatically.
