"""Read Claude Code's session transcript defensively, for the hooks that judge what a session did.

The transcript is JSONL in an internal format with no stability promise: a
typed prompt is a `user` entry whose content is a string, each tool call an
`assistant` entry with a `tool_use` block, and a subagent's calls live in
`<transcript without .jsonl>/subagents/agent-<id>.jsonl` (shapes checked on a
live session, 2026-10-04). Every reader here tolerates missing keys, unknown
entry types and unparseable lines, and returns nothing rather than failing.
Only the file's tail is read, so a multi-hour session stays cheap.
"""

import json
import os

TAIL_BYTES = 2_000_000


def tail_entries(path):
    """The JSON objects in the last TAIL_BYTES of a JSONL file; [] when it cannot be read."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            fh.seek(max(0, size - TAIL_BYTES))
            data = fh.read()
    except (OSError, TypeError, ValueError):
        return []
    lines = data.split(b"\n")
    if size > TAIL_BYTES:
        lines = lines[1:]                        # the first line was cut by the seek
    entries = []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def tool_calls(entries):
    """(name, input, timestamp) of every tool_use block, in order."""
    calls = []
    for entry in entries:
        message = entry.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if entry.get("type") != "assistant" or not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                inp = block.get("input") if isinstance(block.get("input"), dict) else {}
                calls.append((str(block.get("name", "")), inp, entry.get("timestamp")))
    return calls


def last_turn(entries):
    """The entries after the last prompt the user typed (a user entry whose content is a string)."""
    for i in range(len(entries) - 1, -1, -1):
        entry = entries[i]
        message = entry.get("message")
        if (entry.get("type") == "user" and not entry.get("isSidechain")
                and isinstance(message, dict) and isinstance(message.get("content"), str)):
            return entries[i + 1:]
    return entries


def subagents_dir(transcript_path):
    """The folder holding this session's subagent transcripts, or None."""
    if not isinstance(transcript_path, str) or not transcript_path.endswith(".jsonl"):
        return None
    return os.path.join(transcript_path[:-len(".jsonl")], "subagents")


def subagent_transcript(transcript_path, agent_id):
    """The transcript of subagent `agent_id` in this session, or None."""
    folder = subagents_dir(transcript_path)
    if not folder or not isinstance(agent_id, str) or not agent_id or os.sep in agent_id or "/" in agent_id:
        return None
    return os.path.join(folder, f"agent-{agent_id}.jsonl")
