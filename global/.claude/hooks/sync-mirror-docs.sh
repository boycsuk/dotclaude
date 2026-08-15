#!/usr/bin/env bash
# PostToolUse hook: when a rules *.md file is edited, remind that its portable
# mirror may now be stale. The mirrors exist so tools that do not run Claude
# Code (Xcode, sandboxed editors, other assistants) still follow the same
# conventions; docs/conventions.md is the repo-versioned canonical copy and the
# rules file is the copy Claude Code loads (DESIGN.md §17).
#
# DELIVERY: hookSpecificOutput.additionalContext JSON on stdout with exit 0.
# The previous form (stderr + exit 0) never reached the model — with exit 0,
# stderr goes to the debug log only — so the sync obligation this hook exists
# to surface was silently lost. additionalContext delivers without blocking:
# editing a rule is legitimate and must never be gated.
#
# No debounce: this fires only on rule edits, which are rare and each one
# genuinely carries the sync obligation.

INPUT=$(cat)
PATH_EDITED=$(printf '%s' "$INPUT" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('tool_input', {}).get('file_path', ''))" 2>/dev/null || echo "")

# Fire for rule files in either home: a project's own .claude/rules/ or the
# dotclaude repo source global/.claude/rules/ (the installed ~/.claude/rules/
# copy is not editable — guard-central-config blocks it).
case "$PATH_EDITED" in
  *.claude/rules/*.md)
    NOTE="NOTE: you edited a rule ($PATH_EDITED). Its portable mirror may now be stale. Reflect the change in the conventions mirror: templates/project/docs/conventions.md when editing the dotclaude repo, docs/conventions.md inside a deployed project."
    case "$PATH_EDITED" in
      *ai-collaboration.md)
        NOTE="$NOTE If you changed a tone/language/output convention, also update the output style (repo source: global/.claude/output-styles/dotclaude.md, installed as ~/.claude/output-styles/)."
        ;;
    esac
    case "$PATH_EDITED" in
      *workflow.md|*ai-collaboration.md)
        NOTE="$NOTE If you changed a non-negotiable convention, also update the post-compaction digest in hooks/reinject-rules.{sh,ps1}."
        ;;
    esac
    MSG="$NOTE" python3 -c '
import json, os
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                         "additionalContext": os.environ["MSG"]}}))
' 2>/dev/null || true
    ;;
esac

exit 0
