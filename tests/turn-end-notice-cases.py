#!/usr/bin/env python3
"""Behavioural contract for turn-end-notice.py.

Run:  python3 tests/turn-end-notice-cases.py
      python3 tests/turn-end-notice-cases.py --pwsh PATH   # also through PowerShell

The hook is ADVISORY: it must emit `systemMessage` and exit 0, and must never
emit `decision` or exit 2. On Stop, `decision: "block"`, exit 2 AND
`hookSpecificOutput.additionalContext` all continue the conversation — the docs
give additionalContext "the same loop protections as decision: block". A Stop
hook fires on every turn and cannot tell a finished task from a half-done one,
so a hook that resumes the turn interrupts legitimate work. That distinction is
invisible to a test that only asserts "something was printed", which is how
three advisory hooks sat inert on the dead stderr channel for months.

Each case builds a throwaway git repo, pipes one Stop payload through the hook,
and asserts on the parsed stdout.
"""

import json
import os
import shutil
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyhook  # noqa: E402



def git(repo, *args):
    pyhook.git(repo, *args, check=False)


def make_repo(tmp, files, changelog=True, commit_first=True):
    git(tmp, "init", "-q")
    if changelog:
        with open(os.path.join(tmp, "CHANGELOG.md"), "w") as fh:
            fh.write("# Changelog\n")
    if commit_first:
        git(tmp, "add", "-A")
        git(tmp, "commit", "-qm", "init")
    for name, body in files.items():
        path = os.path.join(tmp, name)
        os.makedirs(os.path.dirname(path), exist_ok=True) if "/" in name else None
        with open(path, "w") as fh:
            fh.write(body)
    return tmp


def run_hook(repo, pwsh=None, stop_hook_active=False, session_cwd=None, session=None,
             transcript=None, reply="done"):
    payload = {
        "cwd": session_cwd or repo,
        "hook_event_name": "Stop",
        "stop_hook_active": stop_hook_active,
        # A fresh session per call unless a case shares one: the notice
        # speaks once per change set within a session.
        "session_id": session or uuid.uuid4().hex,
        "last_assistant_message": reply,
    }
    if transcript:
        payload["transcript_path"] = transcript
    code, parsed, err = pyhook.run("turn-end-notice", payload, cwd=repo, pwsh=pwsh)
    if code == 0 and err.strip():
        code = f"0 with stderr {err.strip()[-120:]!r}"
    raw = parsed.get("_unparseable", "") if isinstance(parsed, dict) and "_unparseable" in parsed else \
        (json.dumps(parsed) if parsed else "")
    return code, raw, err.strip()


def parse(out):
    if not out:
        return None
    try:
        return json.loads(out)
    except ValueError:
        return "UNPARSEABLE"


def expect_silent(repo, pwsh, why, **kw):
    rc, out, _ = run_hook(repo, pwsh, **kw)
    if rc != 0:
        return f"{why}: exited {rc}, must always exit 0"
    if out:
        return f"{why}: spoke when it should stay silent — {out[:120]}"
    return None


def expect_message(repo, pwsh, why, must_mention=None, **kw):
    rc, out, _ = run_hook(repo, pwsh, **kw)
    if rc != 0:
        return f"{why}: exited {rc}, must always exit 0"
    data = parse(out)
    if data is None:
        return f"{why}: said nothing when it should warn"
    if data == "UNPARSEABLE":
        return f"{why}: stdout is not valid JSON — {out[:120]}"
    if "systemMessage" not in data:
        return f"{why}: no systemMessage key — {out[:120]}"
    # The whole point: advisory, never resuming the turn.
    if "decision" in data:
        return f"{why}: emitted a `decision` field — that blocks the turn"
    if "hookSpecificOutput" in data:
        return (f"{why}: emitted hookSpecificOutput — additionalContext on Stop "
                f"continues the conversation, which this hook must never do")
    if must_mention and must_mention not in data["systemMessage"]:
        return f"{why}: message never mentions {must_mention!r} — {data['systemMessage'][:120]}"
    return None


def case_code_without_changelog(tmp, pwsh):
    repo = make_repo(tmp, {"app.py": "x = 1\n"})
    return expect_message(repo, pwsh, "code changed, CHANGELOG untouched",
                          must_mention="app.py")


def case_session_in_subdirectory(tmp, pwsh):
    # The session's cwd is a subdirectory while the process starts at the
    # root: the CHANGELOG lookup used the cwd and stayed silent.
    repo = make_repo(tmp, {"src/app.py": "x = 1\n"})
    return expect_message(repo, pwsh, "session in src/, code changed",
                          must_mention="src", session_cwd=os.path.join(repo, "src"))


def case_changelog_updated(tmp, pwsh):
    repo = make_repo(tmp, {"app.py": "x = 1\n", "CHANGELOG.md": "# Changelog\n- x\n"})
    return expect_silent(repo, pwsh, "CHANGELOG was updated alongside the code")


def case_docs_only(tmp, pwsh):
    repo = make_repo(tmp, {"README.md": "hi\n", "notes.txt": "n\n"})
    return expect_silent(repo, pwsh, "only docs changed")


def case_clean_tree(tmp, pwsh):
    repo = make_repo(tmp, {})
    return expect_silent(repo, pwsh, "nothing changed at all")


def case_no_changelog_file(tmp, pwsh):
    repo = make_repo(tmp, {"app.py": "x = 1\n"}, changelog=False)
    return expect_silent(repo, pwsh, "repo keeps no CHANGELOG.md")


def case_not_a_repo(tmp, pwsh):
    with open(os.path.join(tmp, "CHANGELOG.md"), "w") as fh:
        fh.write("# Changelog\n")
    with open(os.path.join(tmp, "app.py"), "w") as fh:
        fh.write("x = 1\n")
    return expect_silent(tmp, pwsh, "not a git repo")


def case_stop_hook_active(tmp, pwsh):
    """Already continuing because of a stop hook: never pile on."""
    repo = make_repo(tmp, {"app.py": "x = 1\n"})
    return expect_silent(repo, pwsh, "stop_hook_active is true",
                         stop_hook_active=True)


def case_untracked_code(tmp, pwsh):
    """An untracked new file is still a code change."""
    repo = make_repo(tmp, {"newmod.py": "y = 2\n"})
    return expect_message(repo, pwsh, "untracked code file", must_mention="newmod.py")


def case_lockfile_only(tmp, pwsh):
    repo = make_repo(tmp, {"package-lock.json": "{}\n", "poetry.lock": "x\n"})
    return expect_silent(repo, pwsh, "only lockfiles/config changed")


def case_missing_cwd(tmp, pwsh):
    """A payload without cwd must not crash or warn about the wrong repo."""
    code, _, err = pyhook.run("turn-end-notice", '{"hook_event_name":"Stop"}', cwd=tmp, pwsh=pwsh)
    if code != 0 or err.strip():
        return f"payload without cwd: exited {code}, stderr {err.strip()[-120:]!r}; must exit 0 silently"
    return None


def case_once_per_change_set(tmp, pwsh):
    """The same changed files at the next turn end say nothing; a new one speaks again."""
    repo = make_repo(tmp, {"app.py": "x = 1\n"})
    session = uuid.uuid4().hex
    problem = (expect_message(repo, pwsh, "first turn end", must_mention="/commit", session=session)
               or expect_silent(repo, pwsh, "same change set, next turn end", session=session))
    if problem:
        return problem
    with open(os.path.join(repo, "other.py"), "w") as fh:
        fh.write("y = 2\n")
    return expect_message(repo, pwsh, "a new changed file", must_mention="2 changed", session=session)


def case_garbage_input(tmp, pwsh):
    code, _, err = pyhook.run("turn-end-notice", "not json at all", cwd=tmp, pwsh=pwsh)
    if code != 0 or err.strip():
        return f"garbage stdin: exited {code}, stderr {err.strip()[-120:]!r}; must exit 0 silently"
    return None


# --- transcript fixtures: the shapes a live Claude Code transcript uses -------

prompt, call, result, transcript = (pyhook.transcript_prompt, pyhook.transcript_call,
                                    pyhook.transcript_result, pyhook.write_transcript)


def tested_repo(tmp):
    """A repo with a test setup (tests/) and no CHANGELOG.md, so only the test notice can speak."""
    return make_repo(tmp, {"tests/test_app.py": "def test_x():\n    pass\n"}, changelog=False)


def edit(repo, rel="app.py", ts="2026-01-01T00:00:01Z"):
    return call("Edit", ts=ts, file_path=os.path.join(repo, rel), old_string="a", new_string="b")


def case_edit_then_pytest(tmp, pwsh):
    repo = tested_repo(tmp)
    t = transcript(tmp, [prompt("fix it"), edit(repo), result(), call("Bash", command="python3 -m pytest -q"), result()])
    return expect_silent(repo, pwsh, "tests ran after the last edit", transcript=t)


def case_tests_before_last_edit(tmp, pwsh):
    repo = tested_repo(tmp)
    t = transcript(tmp, [prompt("fix it"), edit(repo), call("Bash", command="pytest"), edit(repo, "lib.py")])
    return expect_message(repo, pwsh, "an edit after the last test run", must_mention="no test run", transcript=t)


def case_edit_then_ls(tmp, pwsh):
    repo = tested_repo(tmp)
    t = transcript(tmp, [prompt("fix it"), edit(repo), call("Bash", command="ls -la")])
    return expect_message(repo, pwsh, "no test command after the edit", must_mention="app.py", transcript=t)


def case_verify_skill_counts(tmp, pwsh):
    repo = tested_repo(tmp)
    t = transcript(tmp, [prompt("fix it"), edit(repo), call("Skill", skill="global:verify")])
    return expect_silent(repo, pwsh, "/verify after the edit", transcript=t)


def case_docs_edit_is_not_code(tmp, pwsh):
    repo = tested_repo(tmp)
    t = transcript(tmp, [prompt("docs"), edit(repo, "README.md")])
    return expect_silent(repo, pwsh, "only a README edited", transcript=t)


def case_no_test_setup_stays_silent(tmp, pwsh):
    repo = make_repo(tmp, {}, changelog=False)
    t = transcript(tmp, [prompt("fix it"), edit(repo)])
    return expect_silent(repo, pwsh, "a repo with no test setup", transcript=t)


def case_test_notice_once_per_file_set(tmp, pwsh):
    repo = tested_repo(tmp)
    session = uuid.uuid4().hex
    t = transcript(tmp, [prompt("fix it"), edit(repo)])
    return (expect_message(repo, pwsh, "first turn end", must_mention="no test run", transcript=t, session=session)
            or expect_silent(repo, pwsh, "same edited files at the next turn end", transcript=t, session=session))


def case_runner_forms_count(tmp, pwsh):
    repo = tested_repo(tmp)
    for command in ("npm run test -- --watch=false", "cargo test", "python3 tests/run-matrices.py",
                    "go test ./...", "make test", "npx vitest run"):
        t = transcript(tmp, [prompt("fix it"), edit(repo), call("Bash", command=command)], name="t.jsonl")
        problem = expect_silent(repo, pwsh, f"{command!r} is a test run", transcript=t)
        if problem:
            return problem
    return None


def case_echoed_pytest_is_not_a_run(tmp, pwsh):
    repo = tested_repo(tmp)
    t = transcript(tmp, [prompt("fix it"), edit(repo), call("Bash", command="echo 'remember to run pytest'")])
    return expect_message(repo, pwsh, "echo mentioning pytest", must_mention="no test run", transcript=t)


def case_earlier_turn_does_not_count(tmp, pwsh):
    repo = tested_repo(tmp)
    t = transcript(tmp, [prompt("first"), edit(repo), call("Bash", command="pytest"), prompt("second"),
                         call("Bash", command="ls")])
    return expect_silent(repo, pwsh, "the edit and its test run were in an earlier turn", transcript=t)


def case_last_turn_found_in_a_long_transcript(tmp, pwsh):
    repo = tested_repo(tmp)
    t = transcript(tmp, [prompt("fix it"), edit(repo), call("Bash", command="ls")], padding=2_500_000)
    return expect_message(repo, pwsh, "the turn sits after 2.5 MB of history", must_mention="no test run",
                          transcript=t)


def case_subagent_test_run_counts(tmp, pwsh):
    repo = tested_repo(tmp)
    t = transcript(tmp, [prompt("fix it"), edit(repo), call("Agent", subagent_type="debugger", prompt="run tests")])
    os.makedirs(os.path.join(tmp, "session", "subagents"))
    transcript(os.path.join(tmp, "session", "subagents"), [call("Bash", command="pytest -x")], name="agent-a1.jsonl")
    return expect_silent(repo, pwsh, "a subagent ran the tests after the edit", transcript=t)


def case_subagent_before_edit_does_not_count(tmp, pwsh):
    repo = tested_repo(tmp)
    t = transcript(tmp, [prompt("fix it"), edit(repo, ts="2099-01-01T00:00:00Z")])
    os.makedirs(os.path.join(tmp, "session", "subagents"))
    transcript(os.path.join(tmp, "session", "subagents"), [call("Bash", command="pytest")], name="agent-a1.jsonl")
    return expect_message(repo, pwsh, "a subagent transcript older than the last edit", must_mention="no test run",
                          transcript=t)


def case_web_without_sources(tmp, pwsh):
    repo = make_repo(tmp, {}, changelog=False)
    t = transcript(tmp, [prompt("what is new"), call("WebFetch", url="https://example.com", prompt="x")])
    return expect_message(repo, pwsh, "web research, no sources", must_mention="cites no sources", transcript=t,
                          reply="Here is the answer.")


def case_web_with_sources(tmp, pwsh):
    repo = make_repo(tmp, {}, changelog=False)
    t = transcript(tmp, [prompt("what is new"), call("WebSearch", query="x")])
    return expect_silent(repo, pwsh, "web research with a Sources section", transcript=t,
                         reply="Answer.\n\n**Sources:**\n- [Docs](https://example.com)")


def case_web_in_earlier_turn_only(tmp, pwsh):
    repo = make_repo(tmp, {}, changelog=False)
    t = transcript(tmp, [prompt("first"), call("WebFetch", url="https://example.com", prompt="x"), prompt("thanks")])
    return expect_silent(repo, pwsh, "web research only in an earlier turn", transcript=t, reply="You're welcome.")


def case_findings_share_one_line(tmp, pwsh):
    repo = make_repo(tmp, {"app.py": "x = 1\n", "tests/test_app.py": "pass\n"})
    t = transcript(tmp, [prompt("fix"), edit(repo), call("WebFetch", url="https://example.com", prompt="x")])
    problem = expect_message(repo, pwsh, "all three findings", must_mention="CHANGELOG.md", transcript=t, reply="ok")
    if problem:
        return problem
    rc, out, _ = run_hook(repo, pwsh, transcript=t, reply="ok")
    text = (parse(out) or {}).get("systemMessage", "")
    if "no test run" not in text or "cites no sources" not in text or "\n" in text:
        return f"the three findings are not one line: {text!r}"
    return None


def case_missing_transcript_is_harmless(tmp, pwsh):
    repo = tested_repo(tmp)
    return expect_silent(repo, pwsh, "a transcript path that does not exist",
                         transcript=os.path.join(tmp, "nope.jsonl"))


CASES = [
    ("tests after the last edit: silent", case_edit_then_pytest),
    ("an edit after the last test run: notice", case_tests_before_last_edit),
    ("no test command after the edit: notice", case_edit_then_ls),
    ("/verify counts as a test run", case_verify_skill_counts),
    ("a README edit is not code", case_docs_edit_is_not_code),
    ("a repo with no test setup: silent", case_no_test_setup_stays_silent),
    ("the test notice speaks once per file set", case_test_notice_once_per_file_set),
    ("npm/cargo/go/make/vitest and run-matrices count", case_runner_forms_count),
    ("an echo mentioning pytest is not a run", case_echoed_pytest_is_not_a_run),
    ("an earlier turn's edit does not count", case_earlier_turn_does_not_count),
    ("the last turn is found after 2.5 MB of history", case_last_turn_found_in_a_long_transcript),
    ("a subagent's test run counts", case_subagent_test_run_counts),
    ("a subagent run older than the edit does not count", case_subagent_before_edit_does_not_count),
    ("web research without Sources: notice", case_web_without_sources),
    ("web research with Sources: silent", case_web_with_sources),
    ("web research in an earlier turn only: silent", case_web_in_earlier_turn_only),
    ("CHANGELOG, tests and sources share one line", case_findings_share_one_line),
    ("a missing transcript is harmless", case_missing_transcript_is_harmless),
    ("code changed without CHANGELOG warns", case_code_without_changelog),
    ("CHANGELOG updated stays silent", case_changelog_updated),
    ("docs-only change stays silent", case_docs_only),
    ("clean tree stays silent", case_clean_tree),
    ("repo without CHANGELOG.md stays silent", case_no_changelog_file),
    ("non-git directory stays silent", case_not_a_repo),
    ("stop_hook_active stays silent", case_stop_hook_active),
    ("untracked code file warns", case_untracked_code),
    ("lockfile-only change stays silent", case_lockfile_only),
    ("payload without cwd exits cleanly", case_missing_cwd),
    ("a session in a subdirectory still warns", case_session_in_subdirectory),
    ("garbage stdin exits cleanly", case_garbage_input),
    ("speaks once per change set in a session", case_once_per_change_set),
]


def main():
    args = pyhook.cli()
    targets = [(None, "py")]
    if args.pwsh:
        targets.append((args.pwsh, "ps1"))

    total = bad = 0
    for pwsh, label in targets:
        for name, fn in CASES:
            tmp = tempfile.mkdtemp(prefix="changelog-case-")
            try:
                problem = fn(tmp, pwsh)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            total += 1
            if problem:
                bad += 1
            status = "ok  " if problem is None else "BAD "
            print(f"  {status}[{label}] {name}" + (f" — {problem}" if problem else ""))

    return pyhook.finish("turn-end-notice", bad, total, args.pwsh)


if __name__ == "__main__":
    sys.exit(main())
