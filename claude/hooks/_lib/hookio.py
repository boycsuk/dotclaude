"""Hook input/output for dotclaude's Python hooks.

Every Python hook reads one JSON payload on stdin and answers on stdout with a
`hookSpecificOutput` object, or prints nothing. Keeping the encoding here means
each hook states only its decision, and the stdout channel (the one the model
actually sees; stderr at exit 0 reaches only the debug log) cannot be swapped for stderr by accident.
"""

import io
import json
import os
import re
import sys

# Settings keys that switch a guard (or every hook) off. Granting one is the
# user's decision, so the guards ask before any write that sets one to true.
OPT_OUT_KEYS = ("allowPushToMain", "allowCommitTrailers", "disableAllHooks")
_GRANT = re.compile(r"\b(%s)[\"']?\s*[:=]\s*\$?true\b" % "|".join(OPT_OUT_KEYS))


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


_QUOTING = re.compile(r"[\"'\\`]")


def mentions(cmd, word):
    """True when `word` may run in `cmd` once quotes and escapes are removed.

    The cheap prefilter a guard runs before importing the shell parser:
    `g''it`, `gi\\t` and PowerShell's `` com`mit `` all run the word, and a
    case-insensitive filesystem (Windows, default macOS) runs `GIT` as git.
    """
    return word in _QUOTING.sub("", cmd).lower()


def granted_opt_out(text):
    """The opt-out key `text` sets to true (JSON, jq or PowerShell form), or None."""
    m = _GRANT.search(text) if isinstance(text, str) else None
    return m.group(1) if m else None


def first_time(payload, key):
    """True the first time this hook sees `key` in this session, recording it; True without a session_id.

    Lets a reminder that would repeat on every turn or edit speak once. State
    lives in the system temp folder, one small file per session and hook, and
    any error reading or writing it means "first time": a lost reminder is
    worse than a repeated one.
    """
    session = payload.get("session_id")
    if not isinstance(session, str) or not session:
        return True
    import hashlib
    import tempfile
    digest = hashlib.sha1(session.encode("utf-8")).hexdigest()[:16]
    path = os.path.join(tempfile.gettempdir(), "dotclaude-hooks", f"{hook_name()}-{digest}.seen")
    try:
        with open(path, encoding="utf-8") as fh:
            if key in fh.read().splitlines():
                return False
    except OSError:
        pass
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(key.replace("\n", " ") + "\n")
    except OSError:
        pass
    return True


def _emit(obj):
    # Windows consoles default to a legacy code page; the harness reads UTF-8.
    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    out.write(json.dumps(obj, ensure_ascii=False))
    out.flush()


def hook_name():
    """The running hook's file name without .py, e.g. "guard-destructive"."""
    path = getattr(sys.modules.get("__main__"), "__file__", "") or ""
    return os.path.splitext(os.path.basename(path))[0] or "hook"


def _tagged(text):
    # Every message names its hook, so a wrong one leads straight to the
    # file and its tests/<hook>-cases.py matrix.
    return f"[dotclaude {hook_name()}] {text}"


def deny(reason):
    """PreToolUse: refuse the tool call; `reason` is shown to the model."""
    _emit({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                  "permissionDecision": "deny",
                                  "permissionDecisionReason": _tagged(reason)}})


def ask(reason):
    """PreToolUse: route the tool call to the user for confirmation."""
    _emit({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                  "permissionDecision": "ask",
                                  "permissionDecisionReason": _tagged(reason)}})


def context(event, text):
    """Inject advisory text into the model's context for `event`."""
    _emit({"hookSpecificOutput": {"hookEventName": event, "additionalContext": _tagged(text)}})


def notice(text):
    """Stop: show `text` to the user without resuming the turn.

    `systemMessage` is the one Stop output that does not continue the
    conversation: `decision: "block"`, exit 2 and `additionalContext` all do.
    """
    _emit({"systemMessage": _tagged(text)})


FEEDBACK_EXIT = 2


def feedback(text):
    """PostToolUse: show `text` to Claude; return the exit code that delivers it.

    Exit 2 with stderr shows the text to Claude after the tool already ran;
    `decision: "block"` with a `reason` is the documented JSON equivalent,
    adding the reason next to the tool result. The caller returns the value:
    `return hookio.feedback(msg)`.
    """
    err = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
    err.write(_tagged(text.rstrip("\n")) + "\n")
    err.flush()
    return FEEDBACK_EXIT


def _hook_kind(path):
    try:
        with open(path, encoding="utf-8") as fh:
            first = fh.readline()
    except OSError:
        return ""
    return first.partition("# hook-kind:")[2].strip()


def entrypoint(main):
    """Run a hook's `main` and exit with its return code; never exits 1 on a crash.

    An uncaught exception exits 1, which Claude Code treats as a non-blocking
    error, so a crashing guard let the tool call run unjudged. A guard
    therefore asks the user instead, naming itself and the error; every other
    kind exits 0, since a crash in advice must not interrupt the tool. The
    traceback goes to stderr, which at exit 0 reaches the debug log.
    """
    try:
        code = main()
    except Exception as exc:  # noqa: BLE001 — any crash must still produce a decision
        import traceback
        traceback.print_exc()
        path = getattr(sys.modules.get("__main__"), "__file__", "") or ""
        if _hook_kind(path) == "guard":
            ask(f"this guard crashed ({type(exc).__name__}: {exc}), so the command was not checked. "
                f"Approve only if it is safe. A crash that repeats is a bug in "
                f"claude/hooks/{hook_name()}.py: fix it in the dotclaude repo and re-run ./install.sh.")
        code = 0
    sys.exit(code or 0)


def update_input(tool_input):
    """PreToolUse: replace the tool's input with `tool_input`."""
    _emit({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                  "updatedInput": tool_input}})
