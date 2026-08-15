# PostToolUse hook: warns when an edit touches a secret-bearing file or contains
# a literal-looking credential. Exit 2 surfaces the warning to Claude.
#
# Calibration rules, all learned from measured false results (DESIGN.md §26):
#   - Placeholders (*.example/.sample/.template/.dist), markup prose, and this
#     repo's own hook sources are EXEMPT from the path rule. A `.env.example`
#     exists precisely to hold no values (the template ships one and .gitignore
#     whitelists it) and this hook's own path contains "secrets", so editing the
#     detector tripped the detector. Their CONTENT is still scanned.
#   - NOT exempt: .txt (the classic place to paste a key), the .claude/ tree
#     generally (settings.local.json holds tokens), and anything under
#     secrets/ or credentials/ whatever its extension.
#   - The content pattern is case-INsensitive and quote-optional: `API_KEY=` is
#     the universal spelling and the original pattern missed it entirely. It
#     also matches the JSON shape, where the quote precedes the colon.
#   - Lines that READ a secret from the environment are dropped before matching:
#     `token: process.env.X` is a reference, not a literal.
#
# Lockstep sibling of detect-secrets.sh; tests/detect-secrets-cases.py is the
# shared contract (run it with --pwsh).

$rawInput = [Console]::In.ReadToEnd()
try { $data = $rawInput | ConvertFrom-Json } catch { exit 0 }

# file_path covers Edit/Write; notebook_path is NotebookEdit's spelling.
$pathEdited = if ($data.tool_input.file_path) { $data.tool_input.file_path } else { $data.tool_input.notebook_path }
$newContent = if ($data.tool_input.new_string) { $data.tool_input.new_string }
              elseif ($data.tool_input.content) { $data.tool_input.content }
              elseif ($data.tool_input.new_source) { $data.tool_input.new_source }
              elseif ($data.tool_input.edits) {
                  (@($data.tool_input.edits) | ForEach-Object { $_.new_string }) -join "`n"
              } else { $null }

# Normalize separators so the path checks work with both / and \.
# PowerShell's -match is case-insensitive by default, which matches the .sh
# sibling's explicitly lower-cased comparisons.
$normalized = if ($pathEdited) { $pathEdited -replace '\\', '/' } else { "" }

# A file INSIDE a secrets/ or credentials/ directory is never exempt, whatever
# its extension: `secrets/prod.txt` is a secret store, not documentation.
$isSecretStore = $normalized -match '(^|/)(secrets|credentials)/'
$isExempt = (-not $isSecretStore) -and ($normalized -match '(\.(example|sample|template|dist)$)|(\.(example|sample)\.)|(\.(md|mdx|rst)$)|(/hooks/)|(detect-secrets-cases)')

if (-not $isExempt -and $normalized -match '\.env$|\.env\.|secrets|credentials|private.*key|\.pem$|\.p12$') {
    [Console]::Error.WriteLine("WARNING: edited $pathEdited - verify no secrets are being committed.")
    exit 2
}

# Lines dropped before scanning, all anchored to the VALUE position ([:=] and
# what follows) so a mere mention elsewhere on the line grants no immunity:
# env-var reads (a reference is not a literal) and obvious placeholders
# (your-*, changeme, <paste-here> — a real key never contains those words).
$dropRe = '[:=]\s*["'']?(process\.env|os\.environ|getenv|ENV\[)' +
          '|\$\{\{\s*secrets\.' +
          '|[:=]\s*\$\{?[A-Z_]+\}?\s*$' +
          '|[:=]\s*["'']?[^"'' ]*(your[-_]|changeme|change[-_]me|replace|example|placeholder|dummy|xxxx)' +
          '|[:=]\s*["'']?<[^>]+>'
$scannable = ""
if ($newContent) {
    $scannable = ($newContent -split "`n" | Where-Object { $_ -notmatch $dropRe }) -join "`n"
}

# Labelled shape: value chars cover base64/JWT/hex tokens (+ / . -) as well as
# plain keys; the optional leading quote matches the JSON form ("token": "…").
# Compound labels (SECRET_KEY, AWS_SECRET_ACCESS_KEY, ENCRYPTION_KEY) are
# listed explicitly — a bare `\w*key` would false-positive.
$labels = 'api[_-]?key|secret[_-]?access[_-]?key|secret[_-]?key|access[_-]?key|encryption[_-]?key|signing[_-]?key|secret|token|password|passwd|bearer|private[_-]?key'
if ($scannable -and $scannable -match ('(?i)["'']?(' + $labels + ')["'']?\s*[:=]\s*["'']?[A-Za-z0-9_/+.-]{20,}["'']?')) {
    [Console]::Error.WriteLine("WARNING: the edit appears to contain a literal secret. Use environment variables instead.")
    exit 2
}

# Unmistakable prefixes, unattached to any label (gitleaks-style): PEM blocks,
# AWS AKIA ids, GitHub PATs, Slack and GitLab tokens. Case-SENSITIVE (-cmatch)
# — the prefixes are defined that way and folding would invite false positives.
$prefixes = 'BEGIN[A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}|xox[baprs]-[A-Za-z0-9-]{10,}|glpat-[A-Za-z0-9_-]{20}'
if ($scannable -and $scannable -cmatch $prefixes) {
    [Console]::Error.WriteLine("WARNING: the edit appears to contain a literal secret. Use environment variables instead.")
    exit 2
}

exit 0
