"""Hook input/output for dotclaude's Python hooks.

Every Python hook reads one JSON payload on stdin and answers on stdout with a
`hookSpecificOutput` object, or prints nothing. Keeping the encoding here means
each hook states only its decision, and the stdout channel (the one the model
actually sees; stderr at exit 0 reaches only the debug log) cannot be swapped for stderr by accident.
"""

import io
import json
import os
import sys


def read_payload():
    """Return the hook payload as a dict; {} when stdin is empty or not JSON."""
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
        data = json.loads(raw) if raw.strip() else {}
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def project_dir(payload):
    """The project root: CLAUDE_PROJECT_DIR, else the payload's cwd, else cwd."""
    return os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()


def load_json(path):
    """Parse a JSON file; None when it is missing or unparseable."""
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def local_opt_out(payload, key, root=None):
    """True only when .claude/settings.local.json sets `key` to literal true.

    Opt-outs live in the gitignored local file so the choice stays personal
    and is never forced onto teammates. `root` is the
    repository the command acts on; it defaults to the session's project, but
    a guard judging `git -C ../other ...` must read ../other's choice.
    """
    base = root or project_dir(payload)
    data = load_json(os.path.join(base, ".claude", "settings.local.json"))
    return isinstance(data, dict) and data.get(key) is True


def _emit(obj):
    # Windows consoles default to a legacy code page; the harness reads UTF-8.
    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    out.write(json.dumps(obj, ensure_ascii=False))
    out.flush()


def deny(reason):
    """PreToolUse: refuse the tool call; `reason` is shown to the model."""
    _emit({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                  "permissionDecision": "deny",
                                  "permissionDecisionReason": reason}})


def ask(reason):
    """PreToolUse: route the tool call to the user for confirmation."""
    _emit({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                  "permissionDecision": "ask",
                                  "permissionDecisionReason": reason}})


def context(event, text):
    """Inject advisory text into the model's context for `event`."""
    _emit({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}})


def notice(text):
    """Stop: show `text` to the user without resuming the turn.

    `systemMessage` is the one Stop output that does not continue the
    conversation: `decision: "block"`, exit 2 and `additionalContext` all do.
    """
    _emit({"systemMessage": text})


FEEDBACK_EXIT = 2


def feedback(text):
    """PostToolUse: show `text` to Claude; return the exit code that delivers it.

    Exit 2 with stderr is the PostToolUse channel that reaches Claude without
    stopping the turn (`decision: "block"` would stop it, and the tool already
    ran). The caller returns the value: `return hookio.feedback(msg)`.
    """
    err = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
    err.write(text.rstrip("\n") + "\n")
    err.flush()
    return FEEDBACK_EXIT


def update_input(tool_input):
    """PreToolUse: replace the tool's input with `tool_input`."""
    _emit({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                  "updatedInput": tool_input}})
