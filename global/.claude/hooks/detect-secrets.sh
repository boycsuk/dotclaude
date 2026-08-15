#!/usr/bin/env bash
# PostToolUse hook: warns when an edit touches a secret-bearing file or contains
# a literal-looking credential. The edit already happened (PostToolUse can't undo),
# but exit 2 surfaces stderr to Claude so it can revert in the next turn.
#
# Two calibration rules, both learned from measured false results (DESIGN.md §26):
#   - Placeholder files (*.example, *.sample, *.template, *.dist) are EXEMPT
#     from the path rule. Their whole purpose is to document which variables
#     exist without holding values; `/init-project --fullstack` ships a
#     `.env.example` itself and `.gitignore.template` whitelists it explicitly.
#     Warning on every edit of one teaches the model that this hook is noise —
#     and an ignored hook protects nothing. Their CONTENT is still scanned, so
#     a real key pasted into `.env.example` is still caught.
#   - The content pattern is case-INsensitive and does not require quotes.
#     `API_KEY=` is the universal spelling in .env files and constants, and the
#     original case-sensitive, quote-requiring pattern missed it entirely.

INPUT=$(cat)
# file_path covers Edit/Write; notebook_path is NotebookEdit's spelling.
PATH_EDITED=$(printf '%s' "$INPUT" | python3 -c "import sys, json; ti=json.load(sys.stdin).get('tool_input', {}); print(ti.get('file_path') or ti.get('notebook_path') or '')" 2>/dev/null || echo "")
NEW_CONTENT=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
ti = json.load(sys.stdin).get('tool_input', {})
print(ti.get('new_string') or ti.get('content') or ti.get('new_source')
      or '\n'.join(e.get('new_string', '') for e in ti.get('edits', [])))" 2>/dev/null || echo "")

# Files exempt from the PATH rule (their content is still scanned below):
#   - placeholders: *.example, *.sample, *.template, *.dist — including the
#     infix forms (*.example.json, config.sample.yml)
#   - markup prose: a doc named credentials-policy.md writes ABOUT secrets
#   - this repo's own hook sources: detect-secrets.sh matches *secrets* itself,
#     so editing the detector tripped the detector
#
# Deliberately NOT exempt, each for a measured reason:
#   - .txt: a plain-text file is the classic place to paste a key ("notes.txt").
#     Unlike .md it carries no structure suggesting documentation.
#   - .claude/ generally: settings.local.json holds personal tokens. Only the
#     hook sources under .claude/hooks/ are exempt, not the whole tree.
#   - anything under secrets/ or credentials/, whatever the extension:
#     `secrets/prod.txt` is a store, not prose.
# Lower-cased first so the arms are case-insensitive, matching PowerShell's
# -match default (its `.ps1` sibling would otherwise disagree on `SECRETS/`).
PATH_LOWER=$(printf '%s' "$PATH_EDITED" | tr '[:upper:]' '[:lower:]')

IS_EXEMPT=0
case "$PATH_LOWER" in
  */secrets/*|*/credentials/*|secrets/*|credentials/*)        IS_EXEMPT=0 ;;
  *.example|*.sample|*.template|*.dist|*.example.*|*.sample.*) IS_EXEMPT=1 ;;
  *.md|*.mdx|*.rst)                                           IS_EXEMPT=1 ;;
  */hooks/*)                                                  IS_EXEMPT=1 ;;
  *detect-secrets-cases*)                                     IS_EXEMPT=1 ;;
esac

if [ "$IS_EXEMPT" -eq 0 ]; then
  # Match on the lower-cased path here too, so SECRETS/ and .PEM are caught.
  case "$PATH_LOWER" in
    *.env|*.env.*|*secrets*|*credentials*|*private*key*|*.pem|*.p12)
      echo "WARNING: edited $PATH_EDITED — verify no secrets are being committed." >&2
      exit 2
      ;;
  esac
fi

# Content scan. Two shapes are matched:
#   label = <20+ chars>      the assignment form, quoted or bare
#   "label": "<20+ chars>"   the JSON form (quote precedes the colon)
# Value chars cover base64/JWT/hex tokens (+ / . -) as well as plain keys.
#
# Lines dropped before matching, all anchored to the VALUE position ([:=] and
# what follows) so a mere mention elsewhere on the line grants no immunity:
#   - env-var reads: `token: process.env.X` is a reference, not a literal —
#     flagging it would re-introduce the cry-wolf problem the path exemptions
#     fix (DESIGN.md §26). GitHub Actions' `${{ secrets.X }}` keeps its own
#     shape since the reference is not directly after the colon.
#   - obvious placeholders as values (your-*, changeme, <paste-here>, ...):
#     a descriptive 20+ char placeholder in .env.example is recommended
#     practice, and a real key never contains those words.
DROP='[:=][[:space:]]*["'\'']?(process\.env|os\.environ|getenv|ENV\[)'
DROP="$DROP|\\\$\\{\\{[[:space:]]*secrets\\."
DROP="$DROP|[:=][[:space:]]*\\\$\\{?[A-Z_]+\\}?[[:space:]]*\$"
DROP="$DROP|[:=][[:space:]]*[\"']?[^\"' ]*(your[-_]|changeme|change[-_]me|replace|example|placeholder|dummy|xxxx)"
DROP="$DROP|[:=][[:space:]]*[\"']?<[^>]+>"
SCANNABLE=$(printf '%s' "$NEW_CONTENT" | grep -viE "$DROP" || true)

# Labelled shape: compound labels (SECRET_KEY, AWS_SECRET_ACCESS_KEY,
# ENCRYPTION_KEY) are listed explicitly — a bare `\w*key` would false-positive.
# The quote class holds a REAL apostrophe: [\x27] is not a hex escape in ERE
# (it is the set {\,x,2,7}), which silently unmatched every single-quoted value.
LABELS='api[_-]?key|secret[_-]?access[_-]?key|secret[_-]?key|access[_-]?key|encryption[_-]?key|signing[_-]?key|secret|token|password|passwd|bearer|private[_-]?key'
if printf '%s' "$SCANNABLE" | grep -qiE "[\"']?($LABELS)[\"']?[[:space:]]*[:=][[:space:]]*[\"']?[A-Za-z0-9_/+.-]{20,}[\"']?" 2>/dev/null; then
  echo "WARNING: the edit appears to contain a literal secret. Use environment variables instead." >&2
  exit 2
fi

# Unmistakable prefixes, unattached to any label (gitleaks-style): PEM blocks,
# AWS AKIA ids, GitHub PATs, Slack and GitLab tokens. Case-SENSITIVE — the
# prefixes are defined that way and folding would invite false positives.
PREFIXES='BEGIN[A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}|xox[baprs]-[A-Za-z0-9-]{10,}|glpat-[A-Za-z0-9_-]{20}'
if printf '%s' "$SCANNABLE" | grep -qE "$PREFIXES" 2>/dev/null; then
  echo "WARNING: the edit appears to contain a literal secret. Use environment variables instead." >&2
  exit 2
fi

exit 0
