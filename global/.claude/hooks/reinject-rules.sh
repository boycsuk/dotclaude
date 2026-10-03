#!/usr/bin/env bash
# SessionStart hook (matcher: "compact"): re-inject the non-negotiable
# conventions right after a context compaction. CLAUDE.md and rules/ are
# re-read by the harness, but adherence to advisory prose decays when the
# transcript is summarized (DESIGN.md §10). Whatever this prints to
# stdout is added to the fresh context by Claude Code.
#
# Keep the digest SHORT and limited to rules whose only enforcement is
# prose. Deterministic guarantees (guard-destructive, guard-push-main,
# detect-secrets, guard-central-config, guard-commit, guard-dependencies)
# fire regardless and need no
# restating here.
#
# SYNC OBLIGATION: this digest distills rules/workflow.md and
# rules/ai-collaboration.md. If those rules change, update this digest
# (and its .ps1 sibling) — sync-mirror-docs reminds about it on rule edits.

cat <<'EOF'
POST-COMPACTION REMINDER — non-negotiable conventions still in force:
- One branch per feature/fix; atomic commits covering what AND why.
- A task is done only when verified (/verify) and logged in CHANGELOG.md (/commit handles it).
- Use AskUserQuestion for any decision point instead of asking in prose; batch several pending decisions into one call.
- Explain plainly: lead with the outcome, short sentences, keep every fact/name/path exactly; no filler.
- Challenge assumptions; never agree just to be agreeable.
EOF

exit 0
