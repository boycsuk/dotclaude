# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
- CLAUDE.md: the layout tree now lists `check.py`, `tests/`, and the
  `references/` + `scripts/` subtrees of `skills/init-project/` — the validation
  surface "Operating in this repo" leans on was absent from the map.
- CLAUDE.md and DESIGN.md no longer hard-code `check.py`'s check count (it was
  stated as twelve, nine and fourteen in three places while the script printed
  its own live count).

### Fixed
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

### Deprecated

### Removed

### Security

- `guard-push-main.ps1`'s missing timeout (above) was a fail-open on a safety
  hook: on Windows only, and only under a slow or hung `git`.
