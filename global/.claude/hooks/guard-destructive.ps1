# PreToolUse hook: blocks destructive Bash commands.
# Exit 2 = block + stderr to Claude.

$rawInput = [Console]::In.ReadToEnd()
try { $data = $rawInput | ConvertFrom-Json } catch { exit 0 }

$cmd = $data.tool_input.command
if (-not $cmd) { exit 0 }

# Strip heredoc bodies ONLY for a heredoc that provably just writes a file.
#
# Why strip anything: a body being written to a file is data, not code. A
# `cat > notes.md <<'EOF' ... EOF` documenting `rm -rf` is documentation, and
# blocking it costs more than it saves — this hook only sees Bash, so refusing
# the heredoc pushes the model toward Write/Edit, which it never inspects
# (DESIGN.md §26).
#
# Why an ALLOWLIST and not "strip unless it looks like an interpreter": the
# inverted form was tried and was wrong. `docker exec -i c bash <<EOF`,
# `ssh host <<EOF` and `eval "$(cat <<EOF ...)"` all execute their body and were
# all silently stripped. The exemption now requires POSITIVE evidence of a file
# write; unknown shapes fail CLOSED.
#
# Lockstep sibling of guard-destructive.sh; tests/guard-destructive-cases.py is
# the shared contract (run it with --pwsh).
$WRITER = '^\s*(cat\s*>{1,2}\s*[^\s|;&<>()]+|tee\s+(-a\s+)?[^\s|;&<>()]+)\s*<<-?\s*["'']?[A-Za-z_][A-Za-z0-9_]*["'']?\s*$'
$UNSAFE = '[|`]|\$\(|;|&&|\|\||\bsh\b|\bbash\b|\bzsh\b|\bssh\b|\bdocker\b|\bkubectl\b|\beval\b|\bpython[0-9.]*\b|\bnode\b|\bperl\b|\bruby\b'

$lines = @($cmd -split "`n")
$kept = @()
$i = 0
while ($i -lt $lines.Count) {
    $line = $lines[$i]
    $kept += $line
    $m = [regex]::Match($line, "<<-?\s*[""']?([A-Za-z_][A-Za-z0-9_]*)[""']?")
    if (-not $m.Success -or ($line -notmatch $WRITER) -or ($line -match $UNSAFE)) { $i++; continue }
    $delim = $m.Groups[1].Value
    # `<<-` strips leading tabs, so compare on the trimmed line either way.
    $j = $i + 1
    while ($j -lt $lines.Count -and $lines[$j].Trim() -ne $delim) { $j++ }
    if ($j -ge $lines.Count) {
        # Unterminated: there is no body to trust. Keep every line so a
        # dangerous command in a truncated heredoc is still matched.
        $i++
        continue
    }
    $kept += $lines[$j]      # keep the closing delimiter
    $i = $j + 1
}
$cmd = $kept -join "`n"

# Match recursive rm only on truly dangerous paths:
#   /, /*, /etc..., /home..., /usr..., /var..., /opt..., /root, /boot
#   ~, ~/..., $HOME, $HOME/...
#   bare * or .* or ./* (wildcards)
#   .. or ../ (relative parent traversal)
# The recursive flag may appear ANYWHERE among the flags and in any spelling
# (-rf, -fr, -f -r, --recursive): requiring -r first let `rm -fr /` through.
if ($cmd -match 'rm\s+(-[^\s]+\s+)*(-[A-Za-z]*[rR][A-Za-z]*|--recursive)\s+(-[^\s]+\s+)*(/(\s|$|\*)|/(etc|home|usr|var|opt|root|boot|bin|sbin|lib)([\s/]|$)|~([\s/]|$)|\$HOME([\s/]|$)|\*(\s|$)|\./\*|\.\*|\.\.([\s/]|$))') {
    [Console]::Error.WriteLine("BLOCKED: rm -rf on a dangerous path ('$cmd'). The user must run this manually if intentional.")
    exit 2
}

# Central-config writes via Bash: Edit/Write against ~/.claude are blocked by
# guard-central-config, but a redirect, tee, sed -i, cp/mv-into, rm or chmod
# reaches the same files through the one tool that hook never sees. READING
# stays allowed: cp/mv only block with the guarded path as their LAST argument
# (the destination). [^|;&`n]* keeps each check within one command segment.
$homep = '(~|\$HOME|/home/[^ /]+|/Users/[^ /]+|[A-Za-z]:/Users/[^ /]+)'
$ctail = '/\.claude/(settings\.json|(hooks|agents|skills|rules|output-styles|templates)(/[^ ;|&]*)?)'
$cmdN = $cmd -replace '\\', '/'
if ($cmdN -match (">>?\s*[""']?" + $homep + $ctail) -or
    $cmdN -match ("\b(tee|rm|truncate|ln|chmod|chown)\b[^|;&`n]*\s[""']?" + $homep + $ctail) -or
    $cmdN -match ("\bsed\b[^|;&`n]*-i[^|;&`n]*\s[""']?" + $homep + $ctail) -or
    $cmdN -match ("\b(cp|mv|install|rsync)\b[^|;&`n]*\s[""']?" + $homep + $ctail + "[""']?\s*($|[;&|])")) {
    [Console]::Error.WriteLine("BLOCKED: writing to the installed central config (~/.claude/...) via Bash.")
    [Console]::Error.WriteLine("        The installed copy is shared by every project and overwritten by install.ps1.")
    [Console]::Error.WriteLine("        Edit the source in the dotclaude repo (global\.claude\...) and run .\install.ps1 instead.")
    exit 2
}

if ($cmd -match 'git reset --hard($|\s+(origin/)?(main|master|HEAD~))') {
    [Console]::Error.WriteLine("BLOCKED: git reset --hard on a main branch or HEAD~. Ask the user for explicit confirmation.")
    exit 2
}

# Block remote-code execution: piping a download straight into a shell/interpreter.
#   curl ... | sh|bash|zsh|python...   wget ... | sh...   (and 'fetch', 'http')
# This is the classic 'curl | sh' supply-chain vector; deny rules can't catch it
# reliably because the pipe target and flags vary, so it lives here (see DESIGN.md §10).
if ($cmd -match '(curl|wget|fetch|http)\s.*\|\s*(sudo\s+)?(sh|bash|zsh|fish|dash|ksh|python[0-9.]*|perl|ruby|node|php)(\s|$)') {
    [Console]::Error.WriteLine("BLOCKED: piping a network download into a shell/interpreter (remote code execution). The user must run this manually if intentional.")
    exit 2
}

# Block inline interpreter execution: python3 -c '...', node -e '...', ruby -e, perl -e,
# php -r, and 'bash -c'/'sh -c' one-liners. These run arbitrary code the allowlist
# can't inspect. Legit scripts should live in a file the user reviews, not an inline -c.
if ($cmd -match '(^|\s)(python[0-9.]*\s+(-[A-Za-z]*)?-c|node\s+--eval|node\s+-e|deno\s+eval|(ruby|perl)\s+(-[A-Za-z]*)?-e|php\s+-r|(ba|z|da|k)?sh\s+-c)(\s|$)') {
    [Console]::Error.WriteLine("BLOCKED: inline interpreter execution (e.g. python3 -c / node -e / bash -c). Put the code in a reviewable file, or the user runs it manually.")
    exit 2
}

exit 0
