#!/usr/bin/env bash
# PreToolUse hook: blocks force pushes and direct pushes to main/master.
#
# The push-to-main rule is opt-out: a workflow that lives entirely on main
# (solo project, prototype, scratch repo) is legitimate. To opt out, set
# "allowPushToMain": true in .claude/settings.local.json (gitignored, so
# the choice is personal — never forced onto teammates). Force push is
# never opt-out — it can rewrite shared history and stays blocked always.
#
# Everything is decided from the ISOLATED ARGUMENTS OF THE PUSH ITSELF, never
# from the raw command line. Two failure modes motivate that (both were real):
#   - Matching the whole string blocks innocent commands: a commit message
#     containing "+main", or a heredoc that merely writes the words "git push",
#     is not a push. False positives here are expensive — they teach the model
#     that this hook is noise, and it is the one guarantee DESIGN.md §18 calls
#     unconditional.
#   - Matching surface syntax misses real pushes: `+main:main` force-pushes
#     without the --force flag, `HEAD:main` targets main without the word
#     appearing as a token, and a bare `git push` on main names no branch at
#     all. So resolve the refspec DESTINATION, and fall back to the checked-out
#     branch when no refspec is given.

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('tool_input', {}).get('command', ''))" 2>/dev/null || echo "")
[ -z "$CMD" ] && exit 0

# Parse the command into a verdict. Python does the shell-aware tokenising
# (quote stripping, operator splitting) that a regex over the raw string
# cannot do correctly.
VERDICT=$(CMD="$CMD" python3 <<'PY' 2>/dev/null || echo ""
import os, re, shlex, subprocess, sys

cmd = os.environ["CMD"]

# --- Strip file-writer heredoc bodies; keep executed ones -------------------
# Same allowlist as guard-destructive (see its header): a heredoc body piped
# into `cat > file` / `tee file` is data being written, and judging it would
# false-positive on notes that merely contain the words "git push origin
# main". A heredoc fed to an interpreter (`bash <<EOF`) EXECUTES its body, so
# it stays in the scanned text. Unknown shapes fail CLOSED (body kept).
WRITER = re.compile(r"""
    ^\s*
    (?:cat\s*>{1,2}\s*[^\s|;&<>()]+          # cat > file / cat >> file
      |tee\s+(?:-a\s+)?[^\s|;&<>()]+)         # tee file / tee -a file
    \s*<<-?\s*["']?[A-Za-z_][A-Za-z0-9_]*["']?\s*$
""", re.X)
UNSAFE = re.compile(r"[|`]|\$\(|;|&&|\|\||\bsh\b|\bbash\b|\bzsh\b|\bssh\b|\bdocker\b"
                    r"|\bkubectl\b|\beval\b|\bpython[0-9.]*\b|\bnode\b|\bperl\b|\bruby\b")

lines = cmd.split("\n")
kept, i = [], 0
while i < len(lines):
    line = lines[i]
    kept.append(line)
    m = re.search(r"<<-?\s*[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?", line)
    if not m or not WRITER.match(line) or UNSAFE.search(line):
        i += 1
        continue
    delim = m.group(1)
    j = i + 1
    while j < len(lines) and lines[j].strip() != delim:
        j += 1
    if j >= len(lines):              # unterminated — keep everything
        i += 1
        continue
    kept.append(lines[j])            # keep the closing delimiter
    i = j + 1
cmd = "\n".join(kept)

# --- Newlines outside quotes separate commands exactly like ';' -------------
# shlex collapses newlines to whitespace, which used to merge a multi-line
# block into ONE segment: `git add -A\ngit push origin main` was judged by its
# first command and the push sailed through. A newline inside quotes (a
# multi-line commit message) is still part of the token.
res, quote, k, n = [], None, 0, len(cmd)
while k < n:
    ch = cmd[k]
    if quote:
        if ch == "\\" and quote == '"' and k + 1 < n:
            res.append(ch); res.append(cmd[k + 1]); k += 2; continue
        if ch == quote:
            quote = None
        res.append(ch); k += 1; continue
    if ch in ("'", '"'):
        quote = ch; res.append(ch); k += 1; continue
    if ch == "\\" and k + 1 < n and cmd[k + 1] == "\n":
        res.append(" "); k += 2; continue        # line continuation
    if ch == "\n":
        res.append(" ; "); k += 1; continue
    res.append(ch); k += 1
cmd = "".join(res)

try:
    tokens = shlex.split(cmd)
except ValueError:          # unbalanced quotes — not something we can judge
    sys.exit(0)

# Split into separate shell commands so `git commit -m "..." && git push ...`
# is judged on the push alone, and the commit message can never trigger us.
segments, current = [], []
for tok in tokens:
    if tok in ("&&", "||", ";", "|", "&"):
        segments.append(current)
        current = []
    else:
        current.append(tok)
segments.append(current)

def is_git_word(w):
    """The git binary in any spelling: git, git.exe, /path/to/git(.exe)."""
    return (w in ("git", "git.exe") or w.endswith("/git") or w.endswith("/git.exe")
            or w.endswith("\\git") or w.endswith("\\git.exe"))

def is_push(seg):
    """A segment that actually invokes `git push` (not `echo ... push ...`)."""
    if not seg:
        return False
    # Skip a leading `env`/`sudo`-style wrapper and git's own global flags,
    # which may take a value (`git -C /repo push`).
    try:
        gi = next(i for i, w in enumerate(seg) if is_git_word(w))
    except StopIteration:
        return False
    rest = seg[gi + 1:]
    i = 0
    while i < len(rest):
        w = rest[i]
        if w.startswith("-"):
            # Global flags that consume the next argument.
            if w in ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"):
                i += 2
                continue
            i += 1
            continue
        return w == "push"
    return False

pushes = [s for s in segments if is_push(s)]
if not pushes:
    sys.exit(0)                      # nothing to judge

FORCE_FLAGS = ("--force", "--force-with-lease", "--force-if-includes", "-f")

for seg in pushes:
    gi = next(i for i, w in enumerate(seg) if is_git_word(w))
    args = seg[gi + 1:]
    # Drop git's global flags, then the `push` word itself.
    i = 0
    while i < len(args):
        if args[i].startswith("-"):
            i += 2 if args[i] in ("-C", "-c", "--git-dir", "--work-tree",
                                  "--namespace", "--exec-path") else 1
            continue
        break
    args = args[i + 1:]              # everything after `push`

    # --- Force, by flag, by --mirror, or by a leading '+' on a refspec -------
    for a in args:
        if a in FORCE_FLAGS or a.startswith("--force"):
            print("FORCE_FLAG")
            sys.exit(0)
    if "--mirror" in args:           # mirror can rewrite/delete remote refs
        print("MIRROR")
        sys.exit(0)
    positional = [a for a in args if not a.startswith("-")]
    for a in positional:
        if a.startswith("+"):
            print("FORCE_REFSPEC")
            sys.exit(0)

    # --- Which branch would this land on? -----------------------------------
    # Skip flags and their values, then the remote; what remains are refspecs.
    # --signed is NOT here: it is boolean (--signed / --no-signed /
    # --signed=<mode>) and never consumes a separate token — listing it
    # swallowed the remote and let `git push --signed origin HEAD:main` pass.
    VALUED = ("--repo", "-o", "--push-option", "--receive-pack", "--exec",
              "--recurse-submodules")
    cleaned, j = [], 0
    while j < len(args):
        a = args[j]
        if a.startswith("-"):
            j += 2 if a in VALUED else 1
            continue
        cleaned.append(a)
        j += 1

    delete_mode = any(a in ("--delete", "-d") for a in args)
    all_mode = any(a in ("--all", "--branches") for a in args)

    refspecs = cleaned[1:] if cleaned else []      # cleaned[0] is the remote
    targets = []
    for spec in refspecs:
        dst = spec.split(":")[-1]                  # 'HEAD:main' -> 'main'
        dst = re.sub(r"^refs/heads/", "", dst.lstrip("+"))
        # A deletion (--delete flag, or an empty-src ':dst' refspec) is not a
        # push of commits: deleting remote main/master is destructive and
        # never opt-out; deleting a feature branch is legitimate.
        deleting = delete_mode or (":" in spec and spec.split(":", 1)[0].lstrip("+") == "")
        if deleting:
            if dst in ("main", "master"):
                print(f"DELETE:{dst}")
                sys.exit(0)
            continue
        targets.append(dst)

    if all_mode:                     # --all/--branches push main too
        targets.append("main")

    # No refspec at all, or a refspec whose destination is HEAD/@: git
    # resolves it from the checked-out branch, which never appears in the
    # command string. A deletion-only push must NOT fall back to HEAD.
    if (not refspecs and not targets) or any(t in ("HEAD", "@", "") for t in targets):
        try:
            out = subprocess.run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
                                 capture_output=True, text=True, timeout=2)
            if out.returncode == 0 and out.stdout.strip():
                targets = [t for t in targets if t not in ("HEAD", "@", "")]
                targets.append(out.stdout.strip())
        except Exception:
            pass

    for t in targets:
        if t in ("main", "master"):
            print(f"MAIN:{t}")
            sys.exit(0)
PY
)

case "$VERDICT" in
  FORCE_FLAG)
    echo "BLOCKED: force push detected. The user must run this manually if absolutely necessary." >&2
    exit 2
    ;;
  FORCE_REFSPEC)
    echo "BLOCKED: force push detected (a leading '+' on a refspec forces the update)." >&2
    echo "        The user must run this manually if absolutely necessary." >&2
    exit 2
    ;;
  MIRROR)
    echo "BLOCKED: 'git push --mirror' can rewrite or delete remote refs — equivalent to a force push." >&2
    echo "        The user must run this manually if absolutely necessary." >&2
    exit 2
    ;;
  DELETE:*)
    BRANCH="${VERDICT#DELETE:}"
    echo "BLOCKED: this would DELETE the remote '$BRANCH' branch — as destructive as a force push." >&2
    echo "        The user must run this manually if absolutely necessary." >&2
    exit 2
    ;;
  MAIN:*)
    BRANCH="${VERDICT#MAIN:}"
    ALLOW_MAIN=$(python3 -c "
import json, os
p = os.path.join(os.environ.get('CLAUDE_PROJECT_DIR', '.'), '.claude', 'settings.local.json')
try:
    with open(p) as fh:
        print('true' if json.load(fh).get('allowPushToMain') is True else 'false')
except Exception:
    print('false')
" 2>/dev/null || echo "false")
    [ "$ALLOW_MAIN" = "true" ] && exit 0
    echo "BLOCKED: direct push to main/master (target branch: $BRANCH). Use a feature branch and a PR instead." >&2
    echo "        If this project intentionally lives on main, set \"allowPushToMain\": true in .claude/settings.local.json." >&2
    exit 2
    ;;
esac

exit 0
