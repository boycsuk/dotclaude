# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `CHANGELOG.md` at the repo root; every change from here on is logged in it.
- Single-file Python hooks: `global/.claude/hooks/*.py` with a shared `_lib/` (`hookio.py` for hook I/O, `shellwords.py` for shell-aware command parsing). Both installers ship them; `install.ps1` wires them through the Python interpreter it verified, so one file serves Unix and Windows with no `.sh`/`.ps1` twin to drift.
- `check.py` validates `.py` hooks: wiring resolves to the `.py` file, every `.py` hook declares `# hook-kind: guard|advisory`, advisory hooks emit `additionalContext`, guard hooks have a case matrix.
- Obsolete-artifact manifest (`templates/project/obsolete.json`) and `scripts/prune-obsolete.py`: every `init.sh`/`init.ps1` run removes project hook entries that point at hooks dotclaude no longer ships (in `settings.json` and `settings.local.json`) and reports obsolete MCP servers and directories without deleting them. `detect-drift.py` exposes `OBSOLETE_HOOKS`, `OBSOLETE_MCP` and `OBSOLETE_FILES`. Covered by `tests/update-prune-cases.py`.
- `check.py` check 12: `obsolete.json` may not name a hook or MCP fragment dotclaude still ships.
- Both installers print a notice when a re-install removes a hook file, pointing at `/init-project --update` to prune it from projects.
- `--lsp=<plugin>` for `init.sh`/`init.ps1` (repeatable): installs an official Claude Code LSP plugin at project scope via `claude plugin install --scope project`, warning — never failing — when the language-server binary, the `claude` CLI or the plugin name is missing. `templates/project/lsp-plugins.json` maps the 13 official plugins to their binaries and install hints; `/init-project` passes the flag for the detected language and offers it on `--update`. Covered by `tests/lsp-plugin-cases.py`; `check.py` check 13 validates the catalog.
- `--codebase-memory` for `init.sh`/`init.ps1`: merges the `codebase-memory-mcp` server (persistent code graph) into `.mcp.json` and its 13 read-only tools into the project `permissions.allow` by exact name (index-writing and deleting tools stay on ask), through the shared `scripts/merge-permissions.py`. Exit 8 when the binary is missing, with binary-only install options; dotclaude never runs the upstream `install` subcommand. Covered in `tests/mcp-merge-cases.py`.
- Central hooks `code-intel-context.py` (SessionStart and SubagentStart for code-reading agents) and `explore-graph-prompt.py` (PreToolUse on `Agent`, appends to Explore's prompt via `updatedInput`, no permission decision): they tell the model which code-intelligence tools the project has — the LSP plugin, the codebase-memory graph — and when to use each, instead of CLAUDE.md prose or a custom Explore agent. Silent in projects with neither. Covered by `tests/explore-graph-prompt-cases.py`; `check.py` gains the `rewrite` hook kind (must call `hookio.update_input` and have a matrix).
- `guard-commit.py` (PreToolUse Bash/PowerShell): denies attribution trailers (Co-Authored-By / Signed-off-by lines, `-s`, `--signoff`, `--trailer`; opt-out `allowCommitTrailers`), emoji and Spanish commit messages; asks before `--amend` (including `git -C . commit --amend`, which the prefix ask rule missed), commits on main/master (opt-out `allowPushToMain`), commits that leave out an existing CHANGELOG.md, and a `.sh`/`.ps1` pair committed half. Understands `git add` earlier in the same command and `-a`. Covered by `tests/guard-commit-cases.py` (71 cases).
- `guard-dependencies.py` (PreToolUse Bash and Edit|Write): asks before any command that adds a named package — `npm i`, `pnpm add`, `pip3 install`, `python -m pip install`, `uv add`, `cargo add`, `go get` and wrapped forms the prefix rules missed — and before an edit that adds a dependency to a manifest (package.json, pyproject.toml, requirements*.txt, Cargo.toml, go.mod, Gemfile, composer.json, *.csproj). The reason names the packages, flags unpinned versions and gives the audit command. Covered by `tests/guard-dependencies-cases.py` (72 cases).
- `check.py` check 12b: every opt-out a `.py` hook honours must be documented in `settings.local.json.example`.
- `init.sh`/`init.ps1 --update --recursive [dir]`: updates every dotclaude project under a folder. Projects are recognised by the settings stub, `settings.local.json.example` or obsolete hook entries (dependency folders, nested projects and template copies are skipped); each gets the flags its `.mcp.json` implies. It shows the plan and asks before changing anything (`--dry-run`, `--yes`), prunes obsolete hooks, removes obsolete MCP servers and their permissions, and only lists obsolete directories. One implementation in `scripts/update-projects.py`; covered by `tests/update-projects-cases.py`.
- `--remove-obsolete-mcp` for `init.sh`/`init.ps1`: removes the MCP servers listed in `obsolete.json` from `.mcp.json`, with their `mcp__<name>` permission rules.

### Changed
- Both installers set `"outputStyle": "dotclaude"` when the key is absent (never overriding a user's choice); `rules/ai-collaboration.md` keeps only a short fallback of the conventions the style carries (DESIGN.md §36).
- Prose now points at the hooks that enforce it: `workflow.md` (commits), `security.md` (dependencies), the CLAUDE.md template's `Don't` starters, and the `reinject-rules` digest drops the lines `guard-commit` enforces. The trailer policy is now one rule everywhere: denied unless the project sets `allowCommitTrailers` (DESIGN.md §35).
- `CLAUDE.md` constraint #2: new hooks are single-file Python; the `.sh`/`.ps1` lockstep applies to the remaining pairs.
- The Explore agent is no longer described as running on Haiku: since Claude Code v2.1.198 it inherits the session model (`rules/ai-collaboration.md`, template README).

### Removed
- Serena and Graphify: the `--serena` flag (now accepted and ignored with a warning; exit 4 retired), `mcp/serena.json`, `mcp/graphify.json`, `serena-hooks.json` and the project hooks-merge machinery in both init scripts, the `prefer-serena-bash` and `prefer-graphify` hooks, their guidance in rules, the CLAUDE.md template (`{{SERENA_BLOCK}}`), the researcher agent, `/plan-feature`, the init-project skill and READMEs. Existing projects lose the dead hook entries on their next deploy through `obsolete.json`; `/init-project --update` offers to remove the `serena`/`graphify` servers and `.serena/` / `graphify-out/` (DESIGN.md §32).
- `check.py` no longer reads a code-extension list from a hook (check 6 compares the two path-scoped rules only).

### Fixed
- Pre-merge review of this change (all verified by running the hooks): `guard-dependencies` ignored commands on Windows (the tool is named `PowerShell` there); `init.ps1` ran the Microsoft Store `python3` stub, so pruning and the permission merge silently did nothing (both PowerShell scripts now verify a Python that runs, including the `py -3` launcher); `shellwords` missed `timeout`/`nice -n`/`env -u`/`xargs` wrappers, subshells, `if` bodies and `bash -c`; `guard-commit` missed abbreviated long options (`--signo`), `$'...'` messages, heredoc messages containing quotes or apostrophes, message files written earlier in the same command, and PowerShell backtick escapes and here-strings; `guard-dependencies` swallowed package names behind tool-specific flags (`npm i -s x`, `pnpm -w add x`, `npm --prefix web install x`) and, without `tomllib`, read any pyproject/Cargo edit as a new dependency; prune removed Serena's own hooks even while Serena stays installed (now kept until `serena-hooks` is gone); `--trailer 'Closes: #12'` was treated as attribution; the settings scripts rejected BOM-prefixed files and crashed on odd `permissions` shapes; `claude plugin install` could abort `init.ps1` on PowerShell 5.1. check.py now also rejects obsolete matches that hit live hook commands, unwired `.py` hooks and guards that never deny or ask.
- Stale claims: `code-quality.md` said `verify-on-edit` enforces formatting and naming (it runs lint/typecheck for TS/JS, Python, Rust, Go); the CLAUDE.md template did not say `security.md` is path-scoped; `CLAUDE.md` said check.py has twelve checks; DESIGN.md §17 still described an `if:` gate that was removed; the researcher agent said subagents never see the project's tools.

### Security
- The central deny rule `Bash(mkfs.*:*)` blocked nothing on any platform: Claude Code reads a `*` placed before the `:*` suffix literally, so `mkfs.ext4` ran unblocked. It is now `Bash(mkfs.*)`; check.py and install.ps1 strip only a literal `:*` when deriving verbs, and check.py rejects rules that mix the two syntaxes (DESIGN.md §34).

## [0.1.0] - 2026-08-15

### Added
- Initial import: central Claude Code config (`global/.claude/`), per-project template (`templates/project/`), the `/init-project` skill, installers, `check.py` and the hook case matrices.
