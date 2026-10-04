# hook-kind: advisory
"""PostToolUse hook: when an edited file implements a docs/design/ spec, remind Claude to keep the design in step.

A spec in docs/design/ names its source files on a `Code:` line. Editing one of them
can change what the spec (and, with a canvas, the drawing) describes, and a
design that trails its code is how a regenerated spec later resets intentional
changes. Delivered as additionalContext: the edit is legitimate and must never
be gated, and stderr at exit 0 never reaches the model. Silent in projects
without docs/design/, on files no spec names, and on the specs themselves.
"""

import glob
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))

import hookio  # noqa: E402

CODE_LINE = re.compile(r"^\s*-\s*Code:\s*(.+?)\s*$")


def relative(path, root):
    """`path` relative to `root` with forward slashes, or None when it lies outside."""
    if os.path.isabs(path):
        try:
            path = os.path.relpath(path, root)
        except ValueError:                        # another drive on Windows
            return None
        if path == os.pardir or path.startswith(os.pardir + os.sep):
            return None
    return os.path.normcase(os.path.normpath(path.replace("\\", "/"))).replace("\\", "/")


def code_paths(value):
    for item in value.split(","):
        item = item.strip().strip("`").strip()
        if item and not item.startswith("<"):
            yield os.path.normcase(os.path.normpath(item.replace("\\", "/"))).replace("\\", "/")


def specs_naming(target, root):
    hits = []
    for spec in sorted(glob.glob(os.path.join(root, "docs", "design", "**", "README.md"), recursive=True)):
        try:
            with open(spec, encoding="utf-8-sig", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        for line in lines:
            m = CODE_LINE.match(line)
            if m and target in code_paths(m.group(1)):
                hits.append(os.path.relpath(spec, root).replace("\\", "/"))
                break
    return hits


def main():
    payload = hookio.read_payload()
    tool_input = payload.get("tool_input")
    path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    root = hookio.project_dir(payload)
    if not isinstance(path, str) or not path or not os.path.isdir(os.path.join(root, "docs", "design")):
        return 0
    target = relative(path, root)
    if not target or target.startswith("docs/design/"):
        return 0
    specs = specs_naming(target, root)
    if specs:
        hookio.context("PostToolUse", (
            f"NOTE: {target} implements {', '.join(specs)}. If this edit changed what that spec "
            "describes (parameters, layout, sizes, states, copy), keep the design in step before "
            "finishing: with a canvas (docs/design/README.md names one), write the change back into its "
            "artboard, record the new canvas version and regenerate the spec; without one, update the "
            "spec. An `## Accepted deviations` line only for what a canvas cannot draw."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
