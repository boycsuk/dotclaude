# hook-kind: rewrite
"""PreToolUse hook on Agent: append the code-intelligence guidance to Explore's prompt.

The built-in Explore agent can already call the LSP tool and MCP tools, but it
skips CLAUDE.md, so it never learns the project has them. SubagentStart
context reaches it too, yet in a probe the prompt channel carried more weight
when the two competed (DESIGN.md §34), so Explore gets the guidance in its
prompt. Only `prompt` changes; every other input key is passed through.
No permission decision is returned: the call still goes through the user's
normal rules for Agent.
"""

import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))

import codeintel  # noqa: E402
import hookio  # noqa: E402

TARGET_AGENT = "Explore"
MARKER = "[dotclaude code-intel]"


def main():
    payload = hookio.read_payload()
    if payload.get("tool_name") != "Agent":
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict) or tool_input.get("subagent_type") != TARGET_AGENT:
        return 0
    prompt = tool_input.get("prompt")
    if not isinstance(prompt, str) or MARKER in prompt:
        return 0
    text = codeintel.guidance(*codeintel.detect(payload))
    if not text:
        return 0
    hookio.update_input(dict(tool_input, prompt=f"{prompt}\n\n{MARKER}\n{text}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
