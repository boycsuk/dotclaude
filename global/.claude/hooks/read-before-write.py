# hook-kind: advisory
"""PreToolUse hook on Write: a new code file in a folder not read this session gets its siblings named.

The conventions say to read 2-3 sibling files before writing new code in an
area and match them. Written blind, a new file also misses every rule scoped
with `paths:`, which loads when a matching file is READ, not when one is
created (anthropics/claude-code#23478). So when a Write creates a code file in
a folder from which nothing was read or edited this session, this names up to
three siblings, the same extension first and the most recently changed first,
and asks Claude to read them and align the new file. An empty new folder
borrows its parent's siblings.

Advisory, never a decision: a PreToolUse note reaches Claude next to the
tool result, so the file is already written when it arrives, and a convention
is delivered context, not a gate. Once per folder per session. The session's
reads come from the transcript tail (a subagent's from its own transcript);
Grep and Glob do not count, since searching does not show a file's style.
"""

import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))

import bootstrap  # noqa: E402,F401
import hookio  # noqa: E402
from transcript import subagent_transcript, tail_entries, tool_calls  # noqa: E402

CODE_EXTENSIONS = {".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rs", ".java", ".kt",
                   ".kts", ".swift", ".rb", ".php", ".cs", ".c", ".h", ".cpp", ".hpp", ".cc", ".scala", ".sh",
                   ".ps1", ".lua", ".dart", ".vue", ".svelte", ".ex", ".exs"}
SEEN_TOOLS = ("Read", "Edit", "MultiEdit", "Write", "NotebookEdit")
MAX_SIBLINGS = 3


def folder_key(path):
    return os.path.normcase(os.path.realpath(os.path.dirname(os.path.abspath(path.replace("\\", os.sep)))))


def seen_folders(payload):
    """Folders of every file read or edited this session, in the main transcript and the subagent's own."""
    paths = [payload.get("transcript_path"),
             subagent_transcript(payload.get("transcript_path"), payload.get("agent_id"))]
    seen = set()
    for path in paths:
        if not path:
            continue
        for name, inp, _ in tool_calls(tail_entries(path)):
            target = inp.get("file_path") or inp.get("notebook_path")
            if name in SEEN_TOOLS and isinstance(target, str) and target:
                seen.add(folder_key(target))
    return seen


def siblings(folder, target):
    """Up to MAX_SIBLINGS code files in `folder`, same extension as `target` first, newest first."""
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    ext = os.path.splitext(target)[1].lower()
    found = []
    for name in names:
        path = os.path.join(folder, name)
        if name == os.path.basename(target) or os.path.splitext(name)[1].lower() not in CODE_EXTENSIONS:
            continue
        try:
            if os.path.isfile(path):
                found.append((os.path.splitext(name)[1].lower() != ext, -os.path.getmtime(path), path))
        except OSError:
            continue
    return [path for _, _, path in sorted(found)[:MAX_SIBLINGS]]


def main():
    payload = hookio.read_payload()
    tool_input = payload.get("tool_input")
    target = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    if payload.get("tool_name") != "Write" or not isinstance(target, str) or not target:
        return 0
    if os.path.splitext(target)[1].lower() not in CODE_EXTENSIONS or os.path.exists(target):
        return 0
    folder = os.path.dirname(os.path.abspath(target))
    if folder_key(target) in seen_folders(payload):
        return 0
    found = siblings(folder, target) or siblings(os.path.dirname(folder), target)
    if not found or not hookio.first_time(payload, folder_key(target)):
        return 0
    names = ", ".join(found)
    hookio.context("PreToolUse", (
        f"{target} is new and nothing in {folder} was read this session. Read {names} and align the new "
        f"file with them (naming, structure, error handling, imports); reading them also loads any "
        f"path-scoped rules for this area."))
    return 0


if __name__ == "__main__":
    hookio.entrypoint(main)
