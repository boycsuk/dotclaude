# hook-kind: feedback
"""PostToolUse hook: flag new code comments that cite the plan or point into the project's docs.

A comment such as "Step 7, deliberately last" or "see CLAUDE.md, 'Scope
non-goals'" describes the process that produced the code, not the code; once
the plan is done or the doc is renumbered it reads as a riddle. Only the literal
forms are matched — plan positions with a number, and a markdown file cited as
a pointer — so the paraphrased ones stay with rules/code-quality.md and /audit.

It warns instead of denying: the edit already happened, and the patterns are
deliberately narrow, so a rare false hit costs one ignored line. Only comment
text is scanned, never code or strings in prose files, and on an Edit only the
lines the edit added, so a pre-existing comment near the change is not blamed
on it.
"""

import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))

import hookio  # noqa: E402

HASH = ("#",)
SLASH = ("//",)
DASH = ("--",)
C_BLOCK = (("/*", "*/"),)
HTML_BLOCK = (("<!--", "-->"),)
PY_BLOCK = (('"""', '"""'), ("'''", "'''"))

# extension -> (line comment markers, block comment (opener, closer) pairs)
SYNTAX = {}
for exts, syntax in (
    ("py pyi ipynb", (HASH, PY_BLOCK)),
    ("sh bash zsh fish rb pl r yaml yml toml cfg conf tf nix ex exs cmake mk", (HASH, ())),
    ("ps1 psm1 psd1", (HASH, (("<#", "#>"),))),
    ("js jsx ts tsx mjs cjs mts cts rs go c h cc cpp cxx hpp cs java kt kts swift scala dart "
     "zig proto groovy gradle sol jsonc scss less", (SLASH, C_BLOCK)),
    ("php", (SLASH + HASH, C_BLOCK)),
    ("css", ((), C_BLOCK)),
    ("sql", (DASH, C_BLOCK)),
    ("lua hs elm", (DASH, ())),
    ("html htm xml svg", ((), HTML_BLOCK)),
    ("vue svelte astro", (SLASH, C_BLOCK + HTML_BLOCK)),
):
    for ext in exts.split():
        SYNTAX[ext] = syntax
BASENAMES = {"dockerfile": (HASH, ()), "makefile": (HASH, ()), "containerfile": (HASH, ())}

# A C-style block continued from outside the edited hunk still reads " * text".
STAR_CONTINUATION = re.compile(r"^\s*\*(?!/)\s?(.*)$")

PLAN_POSITION = re.compile(r"\b(step|phase|milestone|sprint)\s+#?\d+\b", re.I)
MD = r"[\w./-]*\w\.md\b"
DOC_POINTER = re.compile(
    rf"\b(see|per|cf\.?|refer to|described in|documented in|explained in|according to)\s+(the\s+)?{MD}"
    rf"|{MD}\s*(§|section\s+\d|#\w|,\s*[\"'“])", re.I)

# This hook and its matrix quote the very forms they flag.
SELF = re.compile(r"(^|/)(comment-hygiene\.py|comment-hygiene-cases\.py)$")
MAX_REPORTED = 5


def syntax_for(path):
    norm = path.replace("\\", "/")
    base = norm.rsplit("/", 1)[-1].lower()
    if base in BASENAMES:
        return BASENAMES[base]
    return SYNTAX.get(base.rsplit(".", 1)[-1]) if "." in base else None


def comment_lines(text, syntax):
    """Return (line, comment text) for every line of `text` that carries a comment."""
    markers, blocks = syntax
    found = []
    closer = None
    for line in text.splitlines():
        parts, rest = [], line
        if closer is None and C_BLOCK[0] in blocks:
            star = STAR_CONTINUATION.match(line)
            if star and not any(m in line for m in markers):
                parts.append(star.group(1))
                rest = ""
        while rest:
            if closer:
                end = rest.find(closer)
                if end < 0:
                    parts.append(rest)
                    break
                parts.append(rest[:end])
                rest, closer = rest[end + len(closer):], None
                continue
            hits = [(rest.find(m), m, None) for m in markers if m in rest]
            hits += [(rest.find(o), o, c) for o, c in blocks if o in rest]
            if not hits:
                break
            pos, opener, close = min(hits, key=lambda h: h[0])
            if close is None:
                parts.append(rest[pos + len(opener):])
                break
            rest, closer = rest[pos + len(opener):], close
        if parts:
            found.append((line, " ".join(parts)))
    return found


def offending(text, syntax, old_text=""):
    old_lines = {ln.strip() for ln in old_text.splitlines()}
    hits = []
    for line, comment in comment_lines(text, syntax):
        if line.strip() in old_lines:
            continue
        if PLAN_POSITION.search(comment) or DOC_POINTER.search(comment):
            hits.append(line.strip())
    return hits


def message(path, hits):
    shown = "\n".join(f"  {h[:160]}" for h in hits[:MAX_REPORTED])
    more = f"\n  (+{len(hits) - MAX_REPORTED} more)" if len(hits) > MAX_REPORTED else ""
    return (f"Comment hygiene: comments you just wrote in {path} cite the plan or point into the project's "
            f"docs instead of explaining the code:\n{shown}{more}\n"
            "A comment describes the code as it is, not the process that produced it: no plan steps, phases "
            "or milestones, no pointers such as 'see CLAUDE.md' or 'SPEC.md §4'. Rewrite each to state the "
            "reason itself in one line, or delete it. Links to issues, RFCs and vendor docs are fine; if a "
            "hit is about the code's own subject (an algorithm's step 2), leave it.")


def main():
    payload = hookio.read_payload()
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not isinstance(path, str) or not path or SELF.search(path.replace("\\", "/")):
        return 0
    syntax = syntax_for(path)
    text = tool_input.get("new_string") or tool_input.get("content") or tool_input.get("new_source") or ""
    if syntax is None or not isinstance(text, str) or not text:
        return 0
    old = tool_input.get("old_string")
    hits = offending(text, syntax, old if isinstance(old, str) else "")
    return hookio.feedback(message(path, hits)) if hits else 0


if __name__ == "__main__":
    hookio.entrypoint(main)
