# hook-kind: advisory
"""SessionStart hook (matcher "compact"): re-inject the non-negotiable conventions after compaction.

CLAUDE.md and rules/ are re-read by the harness, but adherence to advisory
prose decays when the transcript is summarized. Keep the digest
SHORT and limited to rules whose only enforcement is prose: the guard hooks
fire regardless and need no restating here.

SYNC OBLIGATION: this digest distills rules/workflow.md and
rules/ai-collaboration.md. If those rules change, update it —
sync-mirror-docs reminds about it on rule edits.
"""

import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))

import hookio  # noqa: E402

DIGEST = """POST-COMPACTION REMINDER — non-negotiable conventions still in force:
- One branch per feature/fix; atomic commits covering what AND why.
- A task is done only when verified (/verify) and logged in CHANGELOG.md (/commit handles it).
- Use AskUserQuestion for any decision point instead of asking in prose; batch several pending decisions into one call.
- Explain plainly: lead with the outcome, short sentences, keep every fact/name/path exactly; no filler.
- Challenge assumptions; never agree just to be agreeable.
- A subagent's findings are hypotheses: verify a claim at the source before it becomes code, config, or an answer."""


def main():
    hookio.read_payload()
    hookio.context("SessionStart", DIGEST)
    return 0


if __name__ == "__main__":
    sys.exit(main())
