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

### Changed
- The Explore agent is no longer described as running on Haiku: since Claude Code v2.1.198 it inherits the session model (`rules/ai-collaboration.md`, template README).

### Removed
- Serena and Graphify: the `--serena` flag (now accepted and ignored with a warning; exit 4 retired), `mcp/serena.json`, `mcp/graphify.json`, `serena-hooks.json` and the project hooks-merge machinery in both init scripts, the `prefer-serena-bash` and `prefer-graphify` hooks, their guidance in rules, the CLAUDE.md template (`{{SERENA_BLOCK}}`), the researcher agent, `/plan-feature`, the init-project skill and READMEs. Existing projects lose the dead hook entries on their next deploy through `obsolete.json`; `/init-project --update` offers to remove the `serena`/`graphify` servers and `.serena/` / `graphify-out/` (DESIGN.md §32).
- `check.py` no longer reads a code-extension list from a hook (check 6 compares the two path-scoped rules only).

## [0.1.0] - 2026-08-15

### Added
- Initial import: central Claude Code config (`global/.claude/`), per-project template (`templates/project/`), the `/init-project` skill, installers, `check.py` and the hook case matrices.
