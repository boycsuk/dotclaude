# hook-kind: advisory
"""SessionStart + SubagentStart hook: tell the model which code-intelligence tools exist.

Replaces guidance that used to live in CLAUDE.md prose (DESIGN.md §33):
prose decays under compaction and never reaches subagents, while this fires
at every session start and resume, after every compaction, and at the start of
every code-reading subagent. Silent (no output) when the project has neither
an official LSP plugin enabled nor the codebase-memory-mcp server.
"""

import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))

import codeintel  # noqa: E402
import hookio  # noqa: E402

EVENTS = ("SessionStart", "SubagentStart")


def main():
    payload = hookio.read_payload()
    event = payload.get("hook_event_name")
    if event not in EVENTS:
        return 0
    text = codeintel.guidance(*codeintel.detect(payload))
    if text:
        hookio.context(event, text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
