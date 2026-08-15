---
name: plan-feature
description: Structures plan mode for new features using the "interview first" pattern. Interviews the user before planning to surface implicit assumptions, then produces a SPEC.md ready to implement in a fresh session. Use proactively when the user describes a non-trivial feature (more than ~3 files, ambiguous requirements, or an architectural decision) before writing any code.
disallowed-tools: Edit NotebookEdit
---

# Plan Feature

For non-trivial features (>3 files, ambiguous requirements, architectural decisions). Output: a `SPEC.md` ready to be implemented in a clean session.

> **If the session is already in plan mode**, writes are blocked until the user approves: put this structure into the native plan and call `ExitPlanMode`, then write `SPEC.md` as the first action after approval. Outside plan mode, write it directly as described below.
>
> The `disallowed-tools` above make "don't implement yet" deterministic for the invocation turn (`Write` stays available for SPEC.md itself); it is not a whole-session guarantee.

## 1. Interview the user

Clarify before planning. At minimum, cover:
- What is the expected end-state behavior?
- Are there technical constraints (performance, compatibility, forbidden dependencies)?
- Which edge cases worry you?
- Are there known tradeoffs (UX vs performance, simple vs flexible, etc.)?

Use **AskUserQuestion** wherever you can offer concrete options — after step 2 you usually can, because the codebase itself suggests the alternatives (which module owns this, which of two existing patterns to follow, which tradeoff to take). Genuinely open questions ("describe the behaviour you want", "what edge cases worry you") go in prose: that is the documented exception in `rules/ai-collaboration.md`.

Do not proceed until you have clear answers. If the user does not know, surface that as an "open question" in the spec rather than guessing.

## 2. Explore the codebase

Before planning, ground the plan in what exists: read the candidate files you would touch. For a feature crossing modules, dispatch the built-in **Explore** agent (fast lookups) or the `researcher` agent (an end-to-end map), and if the project has a Graphify graph, use `get_pr_impact` / `query_graph` for the blast radius.

Every entry in "Files to touch" below must come from this evidence, not from a guess about the layout.

## 3. Produce a structured plan

Once the spec is clear, write a plan with these sections:
- **Context**: why this change is being made — the problem, what prompted it, the intended outcome.
- **Files to touch**: concrete paths, not "the auth file".
- **Steps in order**: prefer **vertical slices** (DB + service + UI for one sub-feature) over horizontal (all DB first, then all API, then all UI). Verticals give end-to-end feedback from step 1.
- **Verification**: how to test the feature works end-to-end (commands to run, manual checks, test cases).
- **What NOT to include**: explicit non-goals to prevent feature creep.
- **Open questions**: anything the user could not fully answer during the interview.

## 4. Write the output

Save the plan to `SPEC.md` at the project root. If a `SPEC.md` already exists, ask via `AskUserQuestion` whether to overwrite it or write `SPEC-<slug>.md` instead — never clobber a spec silently. **Do not implement anything yet.**

`SPEC.md` is a working document, not a deliverable: it is normally left untracked (the template's `.gitignore` does not commit it), and once the feature is implemented, delete it or archive it under `docs/` — decide which with the user at that point.

## 5. Recommend next step

After writing `SPEC.md`, tell the user:
> "SPEC.md is ready. Review it. When you are ready, open a new session and say: 'Implement according to SPEC.md.'"

This prevents context contamination between planning and implementation (one of the most reliable patterns in Claude Code workflows).
