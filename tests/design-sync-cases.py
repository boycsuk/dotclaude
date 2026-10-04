#!/usr/bin/env python3
"""Behavioural contract for design-sync.py.

Run:  python3 tests/design-sync-cases.py
      python3 tests/design-sync-cases.py --pwsh PATH   # also through PowerShell

The hook reminds Claude, after an Edit or Write, that the file it touched is
implemented by a spec in docs/design/ (named by a `Code:` line), so the design is
kept in step. An advisory hook's failure mode is silence, so the matrix asserts
the delivery channel (additionalContext on stdout, exit 0, empty stderr) as
much as when it fires; and it must stay quiet everywhere else, or the reminder
becomes noise.
"""

import argparse
import atexit
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyhook  # noqa: E402

COMPONENT_SPEC = """# DataTable

- Source: `components/data-table/DataTable.dc.html` on the canvas
- Code: `src/components/DataTable.tsx`, src/components/data-table.css
- Purpose: tabular data with paging.
"""

SCREEN_SPEC = """# Orders

- Source: the code (no canvas)
- Code: src\\screens\\Orders.tsx, src/components/DataTable.tsx
- Purpose: every order, newest first.
"""

PLACEHOLDER_SPEC = """# Header

- Code: <path to the component's source>
"""


def scratch():
    path = tempfile.mkdtemp()
    atexit.register(shutil.rmtree, path, True)
    return path


def project(with_design=True):
    root = scratch()
    if with_design:
        for rel, text in (("docs/design/README.md", "# Design\n\n- Canvas: none\n"),
                          ("docs/design/components/data-table/README.md", COMPONENT_SPEC),
                          ("docs/design/screens/orders/README.md", SCREEN_SPEC),
                          ("docs/design/components/header/README.md", PLACEHOLDER_SPEC)):
            path = os.path.join(root, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
    return root


def payload(file_path, tool="Edit"):
    return {"hook_event_name": "PostToolUse", "tool_name": tool,
            "tool_input": {"file_path": file_path, "old_string": "a", "new_string": "b"}}


# (label, with_design, file_path or a callable(root) -> file_path, tool, expected spec paths or [] for silence)
CASES = [
    ("no docs/design/ folder: silent", False, "src/components/DataTable.tsx", "Edit", []),
    ("a file a Code: line names", True, "src/components/DataTable.tsx", "Edit",
     ["docs/design/components/data-table/README.md", "docs/design/screens/orders/README.md"]),
    ("absolute path inside the project", True,
     lambda root: os.path.join(root, "src", "components", "data-table.css"), "Edit",
     ["docs/design/components/data-table/README.md"]),
    ("Windows separators in the Code: line", True, "src/screens/Orders.tsx", "Write",
     ["docs/design/screens/orders/README.md"]),
    ("Windows separators in the edited path", True, "src\\screens\\Orders.tsx", "Edit",
     ["docs/design/screens/orders/README.md"]),
    ("an unrelated file: silent", True, "src/api/client.ts", "Edit", []),
    ("a spec itself: silent", True, "docs/design/components/data-table/README.md", "Edit", []),
    ("a template placeholder never matches", True, "<path to the component's source>", "Edit", []),
    ("a file outside the project: silent", True, "/elsewhere/src/components/DataTable.tsx", "Edit", []),
    ("a name that only shares a suffix: silent", True, "src/components/OldDataTable.tsx", "Edit", []),
]


def run_case(runner, with_design, file_path, tool):
    root = project(with_design)
    target = file_path(root) if callable(file_path) else file_path
    return pyhook.run("design-sync", payload(target, tool), cwd=root,
                      pwsh=PWSH if runner == "ps" else None, env=pyhook.home_env(scratch()))


def context_of(out):
    specific = (out or {}).get("hookSpecificOutput") or {}
    return specific.get("additionalContext"), specific.get("hookEventName")


def main():
    global PWSH
    ap = argparse.ArgumentParser()
    ap.add_argument("--pwsh", help="path to pwsh, to run through the PowerShell command form too")
    args = ap.parse_args()
    PWSH = args.pwsh

    failures, checked = 0, 0
    for runner, _ in pyhook.runners(args.pwsh):
        for label, with_design, file_path, tool, specs in CASES:
            checked += 1
            code, out, err = run_case(runner, with_design, file_path, tool)
            ctx, event = context_of(out)
            problems = []
            if code != 0:
                problems.append(f"rc={code}")
            if err.strip():
                problems.append(f"stderr={err.strip()[:120]!r}")
            if specs:
                if event != "PostToolUse" or not ctx:
                    problems.append(f"no PostToolUse additionalContext: {out!r}"[:200])
                else:
                    missing = [s for s in specs if s not in ctx]
                    if missing:
                        problems.append(f"context does not name {missing}")
            elif out is not None:
                problems.append(f"expected silence, got {out!r}"[:200])
            if problems:
                failures += 1
                print(f"  FAIL [{runner}] {label}: {'; '.join(problems)}")

    # Malformed payloads must never crash an advisory hook.
    for runner, _ in pyhook.runners(args.pwsh):
        for bad in ({}, {"tool_input": "nope"}, {"tool_input": {"file_path": 7}}):
            checked += 1
            code, out, err = pyhook.run("design-sync", bad, cwd=project(),
                                        pwsh=PWSH if runner == "ps" else None,
                                        env=pyhook.home_env(scratch()))
            if code != 0 or out is not None or err.strip():
                failures += 1
                print(f"  FAIL [{runner}] malformed payload {bad!r}: rc={code} out={out!r} err={err[:80]!r}")

    print(f"\n{checked} cases checked")
    if failures:
        print(f"{failures} FAILED")
        return 1
    scope = "python + powershell" if args.pwsh else "python only (pass --pwsh for the Windows form)"
    print(f"All cases pass — {scope}.")
    return 0


PWSH = None

if __name__ == "__main__":
    sys.exit(main())
