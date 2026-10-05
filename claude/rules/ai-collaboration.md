<!--
  No frontmatter / no paths: — always-on (same priority as CLAUDE.md). These
  collaboration conventions (language, asking for input, sub-agents) apply to
  every session regardless of file type. Non-fork subagents load this file
  too, so every byte below is paid in every session AND every dispatch: keep
  it short, and move anything not needed every time to a paths:-scoped rule,
  a skill, or DESIGN.md. This comment is stripped before injection.

  Maintainer note on writing instruction files (moved here from the loaded
  text): do not put all context in a single file. Area-specific instructions
  live in separate files under .claude/rules/. A rule with a paths: field in
  its frontmatter loads only for files matching its globs; a rule without
  paths: loads every session at the same priority as CLAUDE.md (the
  description: field does NOT gate loading — that is a skills concept). The
  main CLAUDE.md stays lightweight (<200 lines). A paths:-scoped rule attaches
  when a matching file is READ (anthropics/claude-code#23478), so read a
  sibling before creating a new source file — rules/workflow.md already asks
  for that.

  The agent list is not repeated below: the Agent tool already shows each
  agent's description, and every central agent's description is listed in
  every session whether the project uses it or not — db-inspector included,
  so it is not free when unused.
-->

# AI Collaboration

## Output style
The full tone and language conventions live in the `dotclaude` output style (`~/.claude/output-styles/dotclaude.md`), which `install.sh` enables unless you chose another style. Minimal fallback if it is off:
- Castilian Spanish (Spain) with the user, English for everything inside the codebase; no emojis; plain language, outcome first, unavoidable jargon glossed on first use.
- Every decision for the user goes through `AskUserQuestion` (2-4 concrete options, several pending decisions batched into one call); prose questions only for genuinely open-ended input.
- Cite sources (`Sources:` with markdown links) when an answer relies on external research.

**If you are a subagent:** report to your caller in English, and skip `/resume-context`, `AskUserQuestion`, the CHANGELOG and the `/commit` steps — they belong to the main session.

## Project context
Descriptive file and folder names; no abbreviations or ad-hoc nesting. Keep `CLAUDE.md` and `CHANGELOG.md` current so the project can be picked up without earlier conversations, and codify a non-obvious decision with `/compound` rather than trusting memory.

Run `/resume-context` when the first request depends on project state (work in flight, recent changes, what is next) or the project is unfamiliar; skip it for a self-contained question.

## Sub-agents
Use the central agents (listed with their descriptions in the Agent tool) proactively: each works in its own context window. For a "where is X / what imports Y" lookup use the built-in **Explore** agent; `researcher` is for a synthesized, cross-module answer.

**Brief a subagent fully.** It sees none of this conversation: state the objective, the boundaries (what not to touch or repeat), the expected output format, and what is already known.

**Review ladder.** `/changes` summarizes the diff; the `code-reviewer` agent reviews a non-trivial change before `/commit`; `/code-review` is a quick bug pass the user starts; `/audit` is for a pre-merge security pass (This-branch scope) or for code at rest.

**Fan out to investigate; apply in series.** Parallel subagents make broad work possible and carry nearly all of its token cost (a wide sweep can burn over a million tokens); applying the results in the main thread is comparatively free. Sweep once and wide, work through the findings sequentially, and verify with the project's tools and tests, never by re-running the sweep. Group agents by module or dimension (single digits), never one per file: findings are usually cross-file. Persist each result to a scratch file as it returns, so a run cut short by a usage limit resumes the missing units instead of restarting.

**A subagent's findings are hypotheses, not facts.** A sweep sounds equally confident whether or not it is right. Before a claim becomes code, configuration, or an answer the user relies on, verify it at the source — the doc page, the file, the command's real output. Check first: anything that contradicts the code in front of you; a version, flag or field name you have not seen yourself; an API described but never quoted; a recommendation whose rationale the report does not show. Delegation moves the reading out of your context, not the responsibility for it.
