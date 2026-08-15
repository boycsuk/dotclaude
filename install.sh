#!/usr/bin/env bash
# dotclaude installer for Linux / macOS / WSL.
#
# Installs the CENTRAL config into ~/.claude/ — hooks, agents, skills, rules,
# output-styles, and the base settings.json. These apply to every project
# automatically (the harness loads ~/.claude/ for all projects), so improving
# the master repo and re-running this script propagates to all your projects
# at once — no per-project update needed.
#
# Also installs the per-project template and the /init-project skill.
#
# Re-running is safe: it overwrites the central artifacts (they are owned by
# this repo) but never clobbers your personal ~/.claude/CLAUDE.md, and it
# MERGES the base settings into ~/.claude/settings.json without dropping your
# own keys (theme, effortLevel, etc.).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${HOME}/.claude"

echo "==> Installing dotclaude into $TARGET"

if ! command -v python3 >/dev/null 2>&1; then
  # python3 is required: the .sh hooks parse Claude Code's JSON input with it
  # (DESIGN.md §5), and the settings merge below uses it. Without it the central
  # guard hooks fail silently and the deny-first safety layer is lost.
  echo "  ! python3 not found — it is required: the .sh hooks parse hook input with it," >&2
  echo "    and this installer merges settings with it. Install python3 (e.g. apt install python3) and re-run." >&2
  exit 1
fi

mkdir -p "$TARGET/templates" "$TARGET/skills"

# --- Central artifacts: hooks, agents, skills, rules, output-styles ----------
# Owned by this repo — but the DIRECTORIES are shared with the user, who may
# keep their own skills/agents/rules there. An `rm -rf` per directory (the
# previous form) silently deleted all of them on every re-install. So: remove
# only the files this repo shipped LAST time (from the manifest), then copy the
# current set and rewrite the manifest. Files the user added are untouched;
# files this repo stops shipping are still cleaned up.
MANIFEST="$TARGET/.dotclaude-manifest"
if [ -f "$MANIFEST" ]; then
  while IFS= read -r rel; do
    case "$rel" in ""|*..*) continue ;; esac
    rm -f "${TARGET:?}/$rel"
  done < "$MANIFEST"
fi

: > "$MANIFEST.tmp"
for dir in hooks agents skills rules output-styles; do
  src="$SCRIPT_DIR/global/.claude/$dir"
  [ -d "$src" ] || continue
  mkdir -p "$TARGET/$dir"
  cp -r "$src/." "$TARGET/$dir/"
  # POSIX find only: -printf is GNU-specific and BSD find (macOS) errors on it,
  # aborting the install mid-run under set -e — after the manifest cleanup.
  (cd "$src" && find . -type f | sed "s|^\./|$dir/|") >> "$MANIFEST.tmp"
done
# Unix uses the .sh hooks; drop the Windows .ps1 siblings (and keep them out of
# the manifest, so a later install does not try to remove files never written).
# Only hooks/ is filtered: a .ps1 anywhere else IS written, so it must stay in
# the manifest or it becomes an unmanaged orphan when the repo stops shipping it.
rm -f "$TARGET/hooks/"*.ps1
grep -v '^hooks/.*\.ps1$' "$MANIFEST.tmp" > "$MANIFEST" || true
rm -f "$MANIFEST.tmp"
chmod +x "$TARGET/hooks/"*.sh 2>/dev/null || true
# Removing a skill's files leaves its directory behind, and an empty
# ~/.claude/skills/<name>/ still shows up in the skill listing as a phantom.
# Prune empty dirs in the trees we own (never the roots themselves).
for dir in skills agents rules output-styles hooks; do
  [ -d "$TARGET/$dir" ] && find "$TARGET/$dir" -mindepth 1 -type d -empty -delete 2>/dev/null || true
done
echo "  - central hooks/agents/skills/rules/output-styles installed (.sh hooks)"

# --- Central settings.json: MERGE into the user's, do not clobber ------------
# We own permissions/hooks/attribution; the user may have their own keys
# (theme, effortLevel, model, ...). Merge ours in, keep theirs.
python3 - "$SCRIPT_DIR/global/.claude/settings.json" "$TARGET/settings.json" <<'PY'
import json, os, sys
src_path, dst_path = sys.argv[1], sys.argv[2]
with open(src_path) as f:
    src = json.load(f)
src.pop("_comment", None)
dst = {}
if os.path.exists(dst_path):
    try:
        with open(dst_path) as f:
            dst = json.load(f)
    except Exception:
        # An unparseable settings.json is almost always a hand-edit typo (a
        # trailing comma). Treating it as empty would silently drop every
        # personal key — theme, model, statusLine, env, outputStyle — so back
        # it up first and say where it went.
        import shutil, time
        backup = "%s.bak-%s" % (dst_path, time.strftime("%Y%m%d-%H%M%S"))
        shutil.copy2(dst_path, backup)
        sys.stderr.write(
            "  ! %s does not parse; your keys could not be preserved.\n"
            "    A copy is saved at %s — merge anything you need back by hand.\n"
            % (dst_path, backup))
        dst = {}
# Repo owns these top-level keys outright (central config). Everything else in
# the user's settings is preserved untouched.
for key in ("permissions", "hooks", "attribution"):
    if key in src:
        dst[key] = src[key]
with open(dst_path, "w") as f:
    json.dump(dst, f, indent=2)
    f.write("\n")
print("  - ~/.claude/settings.json merged (base permissions + hooks; your other keys kept)")
PY

# --- Per-project template and the /init-project skill ------------------------
rm -rf "$TARGET/templates/project"
cp -r "$SCRIPT_DIR/templates/project" "$TARGET/templates/"
echo "  - templates/project/ installed"

rm -rf "$TARGET/skills/init-project"
cp -r "$SCRIPT_DIR/skills/init-project" "$TARGET/skills/"
echo "  - skills/init-project/ installed"

# --- ~/.claude/CLAUDE.md is the USER's own — never touch it ------------------
# The repo's CLAUDE.md is the maintenance guide for THIS repo, not user global
# preferences, so the installer does not copy it anywhere. Your
# ~/.claude/CLAUDE.md (global preferences for all projects) is yours to manage.

# --- Validate the installed central settings ---------------------------------
if python3 -m json.tool "$TARGET/settings.json" >/dev/null 2>&1; then
  echo "  - settings.json valid"
else
  echo "  ! settings.json failed to parse — investigate before using"
  exit 1
fi

echo ""
echo "Done. Central config is in ~/.claude/ and applies to every project."
echo "Open Claude Code in any project and run /init-project to deploy the"
echo "per-project files (CLAUDE.md, docs/, scaffolds)."
