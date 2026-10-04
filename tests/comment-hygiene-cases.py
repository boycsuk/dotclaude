#!/usr/bin/env python3
"""Behavioural contract for comment-hygiene.py.

Run:  python3 tests/comment-hygiene-cases.py
      python3 tests/comment-hygiene-cases.py --pwsh PATH   # also through PowerShell

The hook warns when a newly written code comment cites the plan ("Step 7",
"Phase 2") or points into the project's own docs ("see CLAUDE.md", "SPEC.md
§4"). Both directions matter: a miss lets the comment through, and a warning on
code, strings, prose files or a URL teaches the model to ignore the hook.
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyhook  # noqa: E402

WARN, QUIET = "WARN", "QUIET"

RUST_MODULE_DOC = (
    "//! Step 7, deliberately last: it is the most expensive part and the least\n"
    "//! differentiated from an existing editor.\n"
    "//!\n"
    "//! Read-only by design. Editing belongs in the user's editor; see CLAUDE.md,\n"
    "//! \"Scope non-goals\".\n"
    "pub mod viewer;\n"
)

# (file_path, content, expected, why)
CASES = [
    # --- must warn: the literal forms, in every comment syntax --------------
    ("/p/src/viewer.rs", RUST_MODULE_DOC, WARN, "the reported module doc: plan step + CLAUDE.md pointer"),
    ("/p/app/cache.py", "# Phase 2: wire the cache\ncache = {}\n", WARN, "plan phase in a hash comment"),
    ("/p/app/api.py", 'def get():\n    """Return the list (see SPEC.md §4)."""\n', WARN,
     "pointer inside a docstring"),
    ("/p/src/merge.ts", "const x = 1; // (DESIGN.md §5)\n", WARN, "trailing parenthetical citation"),
    ("/p/src/a.go", "/* Milestone 3: batch writes */\nfunc a() {}\n", WARN, "plan milestone in a C block"),
    ("/p/src/b.c", {"old_string": "int b;", "new_string": " * See CLAUDE.md for why.\nint b;"}, WARN,
     "Edit inside a block comment whose opener is outside the hunk"),
    ("/p/deploy.sh", "# per docs/architecture.md, the cache runs first\n", WARN, "'per <doc>.md' pointer"),
    ("/p/build.ps1", "<# see README.md #>\n$x = 1\n", WARN, "PowerShell block comment"),
    ("/p/web/index.html", "<!-- Step 3: hero section -->\n<main></main>\n", WARN, "HTML comment"),
    ("/p/db/q.sql", "-- see NOTES.md\nSELECT 1;\n", WARN, "SQL line comment"),
    ("/p/Dockerfile", "# step 2 of the rollout\nFROM alpine\n", WARN, "extension-less Dockerfile"),
    ("/p/src/c.js", '/**\n * Implements the parser.\n * Documented in PLAN.md.\n */\n', WARN,
     "multi-line JSDoc block"),
    ("/p/src/d.py", {"old_string": "x = 1\n", "new_string": "# Sprint 4 leftover\nx = 1\n"}, WARN,
     "Edit adding the comment above unchanged code"),
    ("/p/analysis.ipynb", {"notebook_path": "/p/analysis.ipynb", "new_source": "# Phase 1: load\ndf = 1\n"},
     WARN, "a notebook cell"),

    # --- must stay quiet: code, strings, prose, external references ---------
    ("/p/app/loop.py", "step = 2\nfor phase in range(3):\n    pass\n", QUIET, "identifiers are not comments"),
    ("/p/src/wizard.ts", 'const label = "Step 7";\n', QUIET, "a UI string is not a comment"),
    ("/p/docs/guide.md", "See CLAUDE.md, section 2, and Step 7.\n", QUIET, "prose files are not scanned"),
    ("/p/config.json", '{"note": "see CLAUDE.md"}\n', QUIET, "data files have no comments"),
    ("/p/src/e.rs", "// workaround for https://github.com/a/b/issues/12\n", QUIET, "issue links are fine"),
    ("/p/src/f.py", "# RFC 7231 §4.2.1: GET must be safe\n", QUIET, "an external spec with §"),
    ("/p/src/g.ts", "// see https://github.com/a/b/blob/main/README.md\n", QUIET,
     "a URL to an external .md is a link, not an internal pointer"),
    ("/p/tool.py", 'path = root / "CLAUDE.md"  # the project guide is read first\n', QUIET,
     "code whose subject is a markdown file"),
    ("/p/tool.py", "# Writes CHANGELOG.md, section by section\n", QUIET, "describing the file the code writes"),
    ("/p/tool.py", "#!/usr/bin/env python3\n# Step through the list once\n", QUIET, "'step' without a number"),
    ("/p/src/h.py", {"old_string": "# Phase 2 cache\nx = 1\n", "new_string": "# Phase 2 cache\nx = 2\n"}, QUIET,
     "a pre-existing comment the edit only kept"),
    ("/p/src/i.css", ".step-2 { color: red; } /* brand red */\n", QUIET, "CSS selector names are not comments"),
    ("/repo/tests/comment-hygiene-cases.py", "# see CLAUDE.md\n", QUIET, "this matrix quotes the forms it tests"),
    ("/p/notes.txt", "# Step 7\n", QUIET, "plain text has no comment syntax"),
]


def invoke(runner, file_path, content):
    # A dict content is a raw tool_input fragment (Edit's old/new_string, or
    # NotebookEdit's notebook_path+new_source, which gets no file_path); a
    # string is the Write `content` field.
    if isinstance(content, dict):
        tool_input = dict(content)
        if "notebook_path" not in tool_input:
            tool_input["file_path"] = file_path
    else:
        tool_input = {"file_path": file_path, "content": content}
    proc = subprocess.run(runner, input=json.dumps({"tool_input": tool_input}),
                          capture_output=True, text=True, timeout=30)
    return WARN if proc.returncode == 2 else QUIET if proc.returncode == 0 else f"CRASH(rc={proc.returncode})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh", help="path to pwsh, to run through the PowerShell command form too")
    args = ap.parse_args()

    runners = [(label, pyhook.argv("comment-hygiene", pwsh)) for label, pwsh in pyhook.runners(args.pwsh)]

    failures = 0
    for path, content, want, why in CASES:
        results = {}
        for name, runner in runners:
            try:
                results[name] = invoke(runner, path, content)
            except subprocess.TimeoutExpired:
                results[name] = "TIMEOUT"
        if any(got != want for got in results.values()):
            failures += 1
            detail = ", ".join(f"{n}={g}" for n, g in results.items())
            print(f"  FAIL want {want} got {detail} | {path}   ({why})")

    print(f"\n{len(CASES)} cases checked")
    if failures:
        print(f"{failures} FAILED")
        return 1
    scope = "python + powershell" if args.pwsh else "python only (pass --pwsh for the Windows form)"
    print(f"All cases pass — {scope}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
