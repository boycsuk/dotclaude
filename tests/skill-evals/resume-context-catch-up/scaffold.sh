#!/usr/bin/env bash
set -e
git init -q .
printf '# CLAUDE.md\n\nA small CLI that converts CSV to JSON.\n' > CLAUDE.md
printf '# Changelog\n\n## [Unreleased]\n\n### Added\n- CSV header detection.\n' > CHANGELOG.md
git add . && git -c user.name=eval -c user.email=eval@example.com commit -qm "feat: detect CSV headers"
