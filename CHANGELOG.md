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

## [0.1.0] - 2026-08-15

### Added
- Initial import: central Claude Code config (`global/.claude/`), per-project template (`templates/project/`), the `/init-project` skill, installers, `check.py` and the hook case matrices.
