#!/usr/bin/env bash
# PreToolUse hook: blocks destructive Bash commands that could cause data loss.
# Exit 2 = block + stderr goes to Claude as an error message.

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('tool_input', {}).get('command', ''))" 2>/dev/null || echo "")

# Strip heredoc bodies ONLY for a heredoc that provably just writes a file.
#
# Why strip anything: a body being written to a file is data, not code. A
# `cat > notes.md <<'EOF' ... EOF` that documents `rm -rf` is documentation, and
# blocking it costs more than it saves — this hook only sees Bash, so refusing
# the heredoc pushes the model toward Write/Edit, which it never inspects. It
# teaches an escape route precisely when the subject is dangerous shell.
# Measured: writing this repo's own docs and commit messages tripped it three
# times in one session (DESIGN.md §26).
#
# Why an ALLOWLIST and not "strip unless it looks like an interpreter": that
# inverted form was tried and was wrong. Deciding "does this line execute its
# body?" from text has no reliable negative — `docker exec -i c bash <<EOF`,
# `ssh host <<EOF`, and `eval "$(cat <<EOF ...)"` all execute, and all were
# silently stripped. So the exemption now requires POSITIVE evidence of a
# file write: the line must be exactly a cat/tee redirected to a file, with no
# pipe, no command substitution, no chaining, no interpreter anywhere on it.
# Anything else keeps its body in the scanned text and is matched as before —
# unknown shapes fail CLOSED.
CMD=$(CMD="$CMD" python3 <<'PY' 2>/dev/null || printf '%s' "$CMD"
import os, re, sys

cmd = os.environ["CMD"]
lines = cmd.split("\n")

# A "just writes a file" heredoc opener: `cat > f <<EOF`, `cat >> f <<'EOF'`,
# `tee f <<EOF`, optionally preceded by nothing else. Rejects any line carrying
# a pipe, $(...), backticks, ; & && ||, or an interpreter name.
WRITER = re.compile(r"""
    ^\s*
    (?:cat\s*>{1,2}\s*[^\s|;&<>()]+          # cat > file / cat >> file
      |tee\s+(?:-a\s+)?[^\s|;&<>()]+          # tee file / tee -a file
      |cat\s*>{1,2}\s*[^\s|;&<>()]+\s*)
    \s*<<-?\s*["']?[A-Za-z_][A-Za-z0-9_]*["']?\s*$
""", re.X)
UNSAFE = re.compile(r"[|`]|\$\(|;|&&|\|\||\bsh\b|\bbash\b|\bzsh\b|\bssh\b|\bdocker\b"
                    r"|\bkubectl\b|\beval\b|\bpython[0-9.]*\b|\bnode\b|\bperl\b|\bruby\b")

out, i = [], 0
while i < len(lines):
    line = lines[i]
    out.append(line)
    m = re.search(r"<<-?\s*[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?", line)
    if not m or not WRITER.match(line) or UNSAFE.search(line):
        i += 1
        continue
    delim = m.group(1)
    # Scan for the closing delimiter. `<<-` strips leading tabs, so compare on
    # the stripped line either way.
    j = i + 1
    while j < len(lines) and lines[j].strip() != delim:
        j += 1
    if j >= len(lines):
        # Unterminated: there is no body to trust. Keep every line, so a
        # dangerous command in a truncated heredoc is still matched.
        i += 1
        continue
    out.append(lines[j])        # keep the closing delimiter
    i = j + 1
sys.stdout.write("\n".join(out))
PY
)

# Match recursive rm only on truly dangerous paths:
#   /, /*, /etc..., /home..., /usr..., /var..., /opt..., /root, /boot
#   ~, ~/..., $HOME, $HOME/...
#   bare * or ./* or .*
#   .. or ../ (relative parent traversal)
# The recursive flag may appear ANYWHERE among the flags and in any spelling
# (-rf, -fr, -f -r, --recursive): requiring -r first let `rm -fr /` through.
if echo "$CMD" | grep -qE 'rm[[:space:]]+(-[^[:space:]]+[[:space:]]+)*(-[A-Za-z]*[rR][A-Za-z]*|--recursive)[[:space:]]+(-[^[:space:]]+[[:space:]]+)*(/([[:space:]]|$|\*)|/(etc|home|usr|var|opt|root|boot|bin|sbin|lib)([[:space:]/]|$)|~([[:space:]/]|$)|\$HOME([[:space:]/]|$)|\*([[:space:]]|$)|\./\*|\.\*|\.\.([[:space:]/]|$))'; then
  echo "BLOCKED: rm -rf on a dangerous path ('$CMD'). The user must run this manually if intentional." >&2
  exit 2
fi

# Central-config writes via Bash: Edit/Write against ~/.claude are blocked by
# guard-central-config, but a redirect, tee, sed -i, cp/mv-into, rm or chmod
# reaches the same files through the one tool that hook never sees. Without
# this, DESIGN.md §23's "the only way to change a central artifact is the repo
# source" is prose, not a guarantee. READING stays allowed: cat/ls/grep and
# cp FROM central config match nothing here (cp/mv only block with the
# guarded path as their LAST argument, i.e. the destination).
HOMEP='(~|\$HOME|/home/[^ /]+|/Users/[^ /]+)'
CTAIL='/\.claude/(settings\.json|(hooks|agents|skills|rules|output-styles|templates)(/[^ ;|&]*)?)'
if echo "$CMD" | grep -qE ">>?[[:space:]]*[\"']?${HOMEP}${CTAIL}" \
   || echo "$CMD" | grep -qE "\b(tee|rm|truncate|ln|chmod|chown)\b[^|;&]*[[:space:]][\"']?${HOMEP}${CTAIL}" \
   || echo "$CMD" | grep -qE "\bsed\b[^|;&]*-i[^|;&]*[[:space:]][\"']?${HOMEP}${CTAIL}" \
   || echo "$CMD" | grep -qE "\b(cp|mv|install|rsync)\b[^|;&]*[[:space:]][\"']?${HOMEP}${CTAIL}[\"']?[[:space:]]*($|[;&|])"; then
  echo "BLOCKED: writing to the installed central config (~/.claude/...) via Bash." >&2
  echo "        The installed copy is shared by every project and overwritten by install.sh." >&2
  echo "        Edit the source in the dotclaude repo (global/.claude/...) and run ./install.sh instead." >&2
  exit 2
fi

if echo "$CMD" | grep -qE 'git reset --hard($|[[:space:]]+(origin/)?(main|master|HEAD~))'; then
  echo "BLOCKED: git reset --hard on a main branch or HEAD~. Ask the user for explicit confirmation." >&2
  exit 2
fi

# Block remote-code execution: piping a download straight into a shell/interpreter.
#   curl ... | sh|bash|zsh|python...   wget ... | sh...   (and 'fetch', 'http')
# This is the classic 'curl | sh' supply-chain vector; deny rules can't catch it
# reliably because the pipe target and flags vary, so it lives here (see DESIGN.md §10).
if echo "$CMD" | grep -qE '(curl|wget|fetch|http)[[:space:]].*\|[[:space:]]*(sudo[[:space:]]+)?(sh|bash|zsh|fish|dash|ksh|python[0-9.]*|perl|ruby|node|php)([[:space:]]|$)'; then
  echo "BLOCKED: piping a network download into a shell/interpreter (remote code execution). The user must run this manually if intentional." >&2
  exit 2
fi

# Block inline interpreter execution: python3 -c '...', node -e '...', ruby -e, perl -e,
# php -r, and 'bash -c'/'sh -c' one-liners. These run arbitrary code the allowlist
# can't inspect. Legit scripts should live in a file the user reviews, not an inline -c.
if echo "$CMD" | grep -qE '(^|[[:space:]])(python[0-9.]*[[:space:]]+(-[A-Za-z]*)?-c|node[[:space:]]+--eval|node[[:space:]]+-e|deno[[:space:]]+eval|(ruby|perl)[[:space:]]+(-[A-Za-z]*)?-e|php[[:space:]]+-r|(ba|z|da|k)?sh[[:space:]]+-c)([[:space:]]|$)'; then
  echo "BLOCKED: inline interpreter execution (e.g. python3 -c / node -e / bash -c). Put the code in a reviewable file, or the user runs it manually." >&2
  exit 2
fi

exit 0
