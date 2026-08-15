#!/usr/bin/env bash
# SessionStart hook (matcher: "compact"): re-inject the non-negotiable
# conventions right after a context compaction. CLAUDE.md and rules/ are
# re-read by the harness, but adherence to advisory prose decays when the
# transcript is summarized — the same rationale behind the Serena
# drift-prevention hooks (DESIGN.md §10, §13). Whatever this prints to
# stdout is added to the fresh context by Claude Code.
#
# Keep the digest SHORT and limited to rules whose only enforcement is
# prose. Deterministic guarantees (guard-destructive, guard-push-main,
# detect-secrets, guard-central-config) fire regardless and need no
# restating here.
#
# SYNC OBLIGATION: this digest distills rules/workflow.md and
# rules/ai-collaboration.md. If those rules change, update this digest
# (and its .ps1 sibling) — sync-mirror-docs reminds about it on rule edits.

cat <<'EOF'
POST-COMPACTION REMINDER — non-negotiable conventions still in force:
- Never `git commit --amend` or rewrite history without explicit user confirmation.
- No AI signature trailers: never add `Co-Authored-By` / `Signed-off-by` by hand.
- One branch per feature/fix; atomic commits covering what AND why.
- A task is done only when verified (/verify) and logged in CHANGELOG.md (/commit handles it).
- Use AskUserQuestion for any decision point instead of asking in prose; batch several pending decisions into one call.
- Explain plainly: lead with the outcome, short sentences, keep every fact/name/path exactly; no filler.
- If the project has Serena/Graphify (see .mcp.json), prefer graph/symbol tools over grep and whole-file reads.
- Challenge assumptions; never agree just to be agreeable.
EOF

exit 0
