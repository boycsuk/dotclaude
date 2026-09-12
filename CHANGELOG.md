# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `tests/advisory-hooks-cases.py`: a 21-case matrix for `reinject-rules`,
  `sync-mirror-docs`, `prefer-serena-bash` and `prefer-graphify` — the four
  hooks `check.py` silently exempted from the matrix requirement, and the only
  ones whose failure mode is silence. It asserts the delivery contract (exit 0,
  `additionalContext` on stdout, the right `hookEventName`, and silence when
  there is nothing to say), not merely that something was printed: that
  distinction is what the dead-stderr channel passed for months. `check.py`
  now requires their matrix and pins those two assertions.
- `check.py`: a check that every scalar key under `permissions` in
  `settings.json` is actually read by `install.ps1`, which rebuilds the object
  key by key and so drops unknown keys on Windows. `defaultMode` was added that
  way and was caught by this check.
- `permissions.defaultMode: "auto"` in the central `settings.json`, making
  explicit what is already the built-in default on Pro/Max/Team instead of
  inheriting it silently — DESIGN.md §9's model was reasoned when the default
  was Manual. Deny and ask rules are unaffected. Documented in the settings
  comment: `auto` takes effect only from `~/.claude/settings.json`, never from
  a project stub.
- `check.py`: a `script syntax` check that runs `bash -n` over every shipped
  `.sh` and, when `pwsh` is on PATH, parses every `.ps1`. Every other check read
  these files as text, so an unparseable hook passed green (DESIGN.md §32).
- `install.sh` / `install.ps1`: a syntax pre-flight over `global/.claude/hooks/`
  that aborts before copying anything, so a broken hook never reaches
  `~/.claude/` and cannot lock the user out of their own Bash tool.
- DESIGN.md §32, recording the unparseable-hook incident, the bash parser
  limitation behind it, and the recovery deadlock it exposed; the deadlock is
  logged as an open question.
- `tests/inject.py`: a `heredoc-back-into-subshell` regression that folds the
  heredoc back into `$( )`, wired into `tests/check-selftest.sh`. The tidier
  form is the one a future maintainer will reach for, so the test pins it.

### Changed
- `rules/security.md` gains an "Optional hardening: the Bash sandbox" section,
  mirrored in `templates/project/docs/conventions.md`. DESIGN.md §21 decided
  against shipping sandbox config and said to "optionally" point power users at
  it from the rules; that pointer went unwritten, so an audit later re-surfaced
  the sandbox as a missing capability when it was a reasoned decision nobody
  could find. §21 now records that a non-goal only written in DESIGN.md gets
  re-proposed as an oversight.
- CLAUDE.md: the layout tree now lists `check.py`, `tests/`, and the
  `references/` + `scripts/` subtrees of `skills/init-project/` — the validation
  surface "Operating in this repo" leans on was absent from the map.
- CLAUDE.md and DESIGN.md no longer hard-code `check.py`'s check count (it was
  stated as twelve, nine and fourteen in three places while the script printed
  its own live count).

### Fixed
- `guard-push-main.ps1`: renamed the loop variable off `$args`, a PowerShell
  automatic variable. Harmless today (nothing read it back) but a correctness
  landmine in a safety hook.
- `prefer-graphify.ps1`: `break` in every `switch` arm. PowerShell evaluates
  every clause unless told to stop, unlike the `.sh` sibling's `case`, where
  `;;` terminates. The three conditions are mutually exclusive today so nothing
  double-fired, but `verify-on-edit.ps1` already used `break` throughout.
- `init.ps1`: the `.gitignore` merge writes through `Write-Utf8NoBom` instead of
  `Add-Content`, which on PS 5.1 defaults to ANSI and CRLF — mangling non-ASCII
  patterns and mixing line endings in a checkout shared with WSL. Comparison is
  now `-cnotcontains`, matching the `.sh` sibling's case-sensitive `grep -qxF`:
  `-notcontains` treated a user's `thumbs.db` as covering `Thumbs.db`.
- `tests/mcp-merge-cases.py` + `init.ps1`: the "`--xcode` on a non-mac host
  aborts" case was unreachable from a Mac. `$IsMacOS` is an engine variable that
  the `uname` stub cannot reach, and only the force-Darwin hatch existed, so the
  case passed by accident on Linux and inverted on macOS. Added the inverse
  hatch so both verdicts are reachable from either runner.
- `tests/verify-on-edit-cases.py`: the hanging-check expectation is now
  per-runner. The `.ps1` bounds processes with `WaitForExit` and always skips,
  while the `.sh` needs a timeout binary stock macOS lacks — a single scalar
  expectation could not describe both.
- `guard-destructive.sh` / `guard-push-main.sh`: move the Python heredoc out of
  the `$( )` command substitution. Bash mishandles a heredoc inside a command
  substitution when the command is followed by an operator (`||` here): it stops
  treating the quoted body as opaque data and lexes it for parens, quotes and
  backticks while hunting the closing paren, so the Python regexes and comments
  made both scripts unparseable. Since both are `PreToolUse` hooks on `Bash`,
  every Bash call in every project failed, with no way to recover from inside
  Claude Code. The heredoc now runs at top level, writing to a temp file that
  bash reads back. Known bash bug, 4.x onward:
  https://lists.gnu.org/archive/html/bug-bash/2010-07/msg00043.html
- `verify-on-edit.sh`: detect `timeout` / `gtimeout` instead of assuming
  `timeout` exists. It is GNU coreutils and is absent from a stock macOS, so
  under `set -e` every `run()` failed and **every edit to a code file reported a
  phantom lint error** — on every macOS project, the platform this hook is most
  used on. With neither binary the checks run unbounded, where the 60s per-hook
  budget in `settings.json` is still a backstop. The `.ps1` sibling was never
  affected: it bounds processes with `WaitForExit`, which needs no external
  binary. Its matrix case is now platform-aware rather than unpassable on macOS.
- `guard-push-main.ps1`: bound the `git symbolic-ref` branch lookup to 2s, as the
  `.sh` sibling already did. Unbounded, a hung git exceeded the hook's 5s budget;
  the harness then cancels the hook and discards its verdict, so a push to main
  proceeded unjudged on Windows.
- `install.ps1`: derive `attribution` from the source `settings.json` instead of
  hard-coding it, and skip null-valued owned keys so the merge matches
  `install.sh` (which copies an owned key only when present).
- `init.ps1`: check `$LASTEXITCODE` after `graphify hook install`. A native
  non-zero exit does not throw in PowerShell, so the `try/catch` never fired and
  a failed install printed the success line.
- CLAUDE.md constraint 3 described `install.sh` as overwriting the central
  artifacts "wholesale" — the anti-pattern the manifest mechanism exists to
  prevent, after it deleted users' own skills/agents/rules on re-install.
  `install.sh`'s own header carried the same stale claim.
- `templates/project/README.md`: the central artifacts install from
  `global/.claude/`, not the repo's non-existent top-level `.claude/`.
- `templates/project/.claude/serena-hooks.json`: the comment advertised stderr as
  the advisory channel — the dead channel the §17 fix replaced with
  `hookSpecificOutput.additionalContext`.
- `tests/guard-central-config-cases.py`: the `~/.Claude/settings.json` case
  hard-coded ALLOW for the `.sh`, which is correct only on a case-sensitive
  filesystem. On macOS the hook folds both paths (APFS is case-insensitive, so
  it really is the guarded file) and returns BLOCK, making the matrix unpassable
  on the maintainer's own machine. The expectation is now platform-aware.

### Deprecated

### Removed

### Security

- `guard-push-main.ps1`'s missing timeout (above) was a fail-open on a safety
  hook: on Windows only, and only under a slow or hung `git`.
