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
> run only when the option the user confirmed includes them, and the branch is
> deleted only when the user also picked **Delete `<branch>` after merging**
> in that confirmation.
>
> Note: the `Bash(git commit:*)` grant above covers the invocation turn only;
> it has expired by the time the user confirms, so the actual commit runs
> under the session's normal Bash permission (central settings, DESIGN.md §9).

## 1. Current state

```!
git status
git diff --stat
```

Then run `git log --oneline -5` with the Bash tool — step 5 follows the convention of those messages. On a repository with no commits yet it fails with exit 128; that is harmless here (there is no convention yet, so use step 5's default) and is why it is not in the block above: a failing injected command aborts the whole skill, which would break the first `/commit` after `/init-project`.

## 2. Verify

Before committing, run the `/verify` skill (it owns the tests + lint + typecheck chain and the stack detection — do not reimplement those commands here). If `/verify` reports a failure, **stop** — do not commit.

You may skip re-running it, and say so, when a `/verify` pass was reported in this session **after the last edit to any file outside this list**: `docs/**`, `CHANGELOG.md`, `README.md`, `CONTRIBUTING.md`. Edits to those cannot change what the suite tests, so the usual chain `/verify` → `/update-docs` → `/commit` runs the suite once. Any other edit since the pass — code, tests, config, a lockfile, or any other `.md` (`CLAUDE.md`, skills, rules and prompts are instructions, not documentation) — means re-running it. If the project's verification reads those files too (doctests over the README or docs, a Markdown linter, a link checker, a validator over the docs), the exemption does not apply.

## 3. Show the full diff

Lockfiles are excluded here — they are noise at diff level and still show up in the `--stat` above.

```!
git diff -- ':(exclude)package-lock.json' ':(exclude)pnpm-lock.yaml' ':(exclude)yarn.lock' ':(exclude)bun.lockb' ':(exclude)*.lock' ':(exclude)go.sum'
git diff --staged -- ':(exclude)package-lock.json' ':(exclude)pnpm-lock.yaml' ':(exclude)yarn.lock' ':(exclude)bun.lockb' ':(exclude)*.lock' ':(exclude)go.sum'
```

Analyze what changed. If there are untracked files that look relevant, propose adding them **by name**. Never `git add -A` or `git add .` without listing the files first. Untracked files do not appear in any diff — `Read` each one you intend to propose (or at least its head) before proposing it, and flag anything that looks like a secret, a build artifact, or an accidental dump instead of adding it. Your read of the diff for secrets does not see the excluded lockfiles; the `guard-commit` hook still scans every staged file, lockfiles included, before the commit runs.

While analyzing, collect the questions for step 4 (ask none of them yet):
- **Branch.** If you are on `main`/`master` and `allowPushToMain` is not set in `.claude/settings.local.json`, say so and prepare the offer to create a `feature/<name>` / `fix/<name>` branch first — `guard-push-main` will block the push later anyway, so surfacing it here saves a rewrite.
- **Docs.** If the diff looks like a contract change — a new or changed route or endpoint, screen or component, design token, or user-facing capability — and no file under `docs/` changed, say so and prepare the offer: **Run `/update-docs` first** / **Commit anyway**. This is a heuristic, never a block: the project's `CLAUDE.md` asks for `/update-docs` before `/commit`, and this catches the times it was skipped.

## 4. Update CHANGELOG.md

If the project has no `CHANGELOG.md`, prepare the question whether to create one (Keep a Changelog 1.1.0 skeleton) or skip this step — never invent one silently.

Ask every question collected in step 3 and this one in **one** `AskUserQuestion` call, one question each (at most three, so the call stays within its limits). Then act on the answers: create the branch if chosen; if the user chose **Run `/update-docs` first**, run it, then walk this skill again from step 1, re-running its commands with the Bash tool (the injected output is now stale) — the other answers still stand and are not asked again.

If `CHANGELOG.md` exists without an `## [Unreleased]` section, add one at the top; if it follows a different format, match that format instead.

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

On a feature branch, the same call carries a second, separate question: **Delete `<branch>` after merging** / **Keep it**. It takes effect only when the confirmed option includes the merge and step 7 runs to the end without stopping; otherwise the branch stays, and say so. Answering it alone authorizes nothing.

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
6. If the user chose **Delete `<branch>` after merging** in the confirmation (step 6): `git branch -d <branch>`, which refuses a branch that is not fully merged. Otherwise keep it.

From main (**Commit and push**): `git push` after the commit; if it is rejected because the remote moved, report and stop.

## Forbidden

- Never use `--amend` without explicit user request.
- Never use `--no-verify`. If a pre-commit hook fails, fix the underlying cause.
- Never add `Co-Authored-By` or similar trailers automatically.
