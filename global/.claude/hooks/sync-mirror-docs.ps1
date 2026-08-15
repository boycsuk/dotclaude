# PostToolUse hook: when a rules *.md file is edited, remind that its portable
# mirror may now be stale. docs/conventions.md is the repo-versioned canonical
# copy and the rules file is the copy Claude Code loads (DESIGN.md §17).
#
# DELIVERY: hookSpecificOutput.additionalContext JSON on stdout with exit 0.
# The previous form (stderr + exit 0) never reached the model — with exit 0,
# stderr goes to the debug log only. additionalContext delivers without
# blocking: editing a rule is legitimate and must never be gated.
# Lockstep sibling of sync-mirror-docs.sh.

$rawInput = [Console]::In.ReadToEnd()
try { $data = $rawInput | ConvertFrom-Json } catch { exit 0 }

$pathEdited = $data.tool_input.file_path
if (-not $pathEdited) { exit 0 }

# Normalize separators so the match works with both / and \.
$normalized = $pathEdited -replace '\\', '/'

if ($normalized -match '\.claude/rules/.*\.md$') {
    $note = "NOTE: you edited a rule ($pathEdited). Its portable mirror may now be stale. Reflect the change in the conventions mirror: templates/project/docs/conventions.md when editing the dotclaude repo, docs/conventions.md inside a deployed project."
    if ($normalized -match 'ai-collaboration\.md$') {
        $note += " If you changed a tone/language/output convention, also update the output style (repo source: global/.claude/output-styles/dotclaude.md, installed as ~/.claude/output-styles/)."
    }
    if ($normalized -match '(workflow|ai-collaboration)\.md$') {
        $note += " If you changed a non-negotiable convention, also update the post-compaction digest in hooks/reinject-rules.{sh,ps1}."
    }
    $payload = @{ hookSpecificOutput = @{ hookEventName = "PostToolUse"; additionalContext = $note } } | ConvertTo-Json -Compress -Depth 3
    [Console]::Out.WriteLine($payload)
}

exit 0
