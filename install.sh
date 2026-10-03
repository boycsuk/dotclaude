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
# Re-running is safe: it refreshes the central artifacts it owns by removing
# only the files it shipped last time (see the manifest below), so your own
# skills/agents/rules in those directories survive. It never clobbers your
# personal ~/.claude/CLAUDE.md. In ~/.claude/settings.json it keeps every key
# you own (theme, env, ...), seeds defaults only when absent, and REPLACES the
# keys dotclaude owns (permissions, hooks, attribution) — saving a backup first
# whenever your file had entries of its own there.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${HOME}/.claude"

echo "==> Installing dotclaude into $TARGET"

# `--version`, not `command -v`: macOS ships a python3 stub that exists but only
# offers to install the Command Line Tools.
if ! python3 --version >/dev/null 2>&1; then
  # python3 is required: the .py hooks are Python, the .sh hooks parse Claude
  # Code's JSON input with it (DESIGN.md §5), and the settings merge below uses
  # it. Without it the central guard hooks fail silently.
  echo "  ! python3 not found — it is required: the hooks run on it or parse hook input with it," >&2
  echo "    and this installer merges settings with it. Install python3 (e.g. apt install python3) and re-run." >&2
  exit 1
fi

# --- Syntax pre-flight: never install a hook that cannot be parsed -----------
# A hook that fails to parse is not a degraded hook, it is a wall: the central
# guards run on PreToolUse for Bash, so an unparseable one makes EVERY Bash call
# in EVERY project fail. That state is also unrecoverable from inside Claude
# Code — the broken hook blocks the `install.sh` that would replace it, and
# guard-central-config blocks editing the installed copy (DESIGN.md §32). So
# check before copying: abort with the source tree untouched and the previously
# installed (working) hooks still in place.
for hook in "$SCRIPT_DIR"/global/.claude/hooks/*.sh; do
  [ -f "$hook" ] || continue
  if ! parse_err=$(bash -n "$hook" 2>&1); then
    echo "  ! $(basename "$hook") does not parse — aborting before anything is copied." >&2
    printf '%s\n' "$parse_err" | sed 's/^/    /' >&2
    echo "    Your currently installed hooks are untouched. Fix the source and re-run." >&2
    exit 1
  fi
done
# Same for the Python hooks: one that fails to compile exits 1, a non-blocking
# error, so the guard would be silently off rather than a wall — just as bad.
python3 - "$SCRIPT_DIR"/global/.claude/hooks/*.py "$SCRIPT_DIR"/global/.claude/hooks/_lib/*.py <<'PY' || exit 1
import sys
for path in sys.argv[1:]:
    try:
        with open(path, encoding="utf-8") as fh:
            compile(fh.read(), path, "exec")
    except SyntaxError as exc:
        sys.stderr.write("  ! %s does not compile (line %s: %s) — aborting before anything is copied.\n"
                         "    Your currently installed hooks are untouched. Fix the source and re-run.\n"
                         % (path.rsplit("/", 1)[-1], exc.lineno, exc.msg))
        sys.exit(1)
PY

mkdir -p "$TARGET/templates" "$TARGET/skills"

# --- Central artifacts: hooks, agents, skills, rules, output-styles ----------
# Owned by this repo — but the DIRECTORIES are shared with the user, who may
# keep their own skills/agents/rules there. An `rm -rf` per directory (the
# previous form) silently deleted all of them on every re-install. So: remove
# only the files this repo shipped LAST time (from the manifest), then copy the
# current set and rewrite the manifest. Files the user added are untouched;
# files this repo stops shipping are still cleaned up.
MANIFEST="$TARGET/.dotclaude-manifest"
EMPTIED="$(mktemp)"
trap 'rm -f "$EMPTIED"' EXIT
if [ -f "$MANIFEST" ]; then
  while IFS= read -r rel; do
    case "$rel" in ""|*..*) continue ;; esac
    rm -f "${TARGET:?}/$rel"
    dirname "$rel" >> "$EMPTIED"
  done < "$MANIFEST"
fi

# Every file this install writes. Unix uses the .sh hooks, so the Windows .ps1
# siblings in hooks/ are never copied (a .ps1 anywhere else IS written and
# tracked). Copying them and deleting `hooks/*.ps1` afterwards also deleted
# the user's own .ps1 hooks.
: > "$MANIFEST.tmp"
for dir in hooks agents skills rules output-styles; do
  [ -d "$SCRIPT_DIR/global/.claude/$dir" ] || continue
  # POSIX find only: -printf is GNU-specific and BSD find (macOS) errors on it,
  # aborting the install mid-run under set -e — after the manifest cleanup.
  (cd "$SCRIPT_DIR/global/.claude/$dir" && find . -type f ! -path '*/__pycache__/*' \
    | sed "s|^\./|$dir/|") >> "$MANIFEST.tmp"
done
grep -v '^hooks/.*\.ps1$' "$MANIFEST.tmp" > "$MANIFEST.new" || true
rm -f "$MANIFEST.tmp"

# A file of the user's that happens to share a shipped name would be
# overwritten and then adopted into the manifest — deleted for good the day
# the repo stops shipping it. Keep a copy and say so.
while IFS= read -r rel; do
  [ -e "$TARGET/$rel" ] || continue
  if [ ! -f "$MANIFEST" ] || ! grep -qxF "$rel" "$MANIFEST"; then
    cp -p "$TARGET/$rel" "$TARGET/$rel.user-backup"
    echo "  ! ~/.claude/$rel was yours, not dotclaude's; saved as $rel.user-backup before replacing it"
  fi
done < "$MANIFEST.new"

for dir in hooks agents skills rules output-styles; do
  src="$SCRIPT_DIR/global/.claude/$dir"
  [ -d "$src" ] || continue
  mkdir -p "$TARGET/$dir"
  # A dev checkout that ran the Python hooks or tests holds __pycache__ dirs;
  # shipping them would leave unmanaged files in a repo-owned tree.
  if [ "$dir" = hooks ]; then
    (cd "$src" && tar -cf - --exclude=__pycache__ --exclude='*.ps1' .) | (cd "$TARGET/$dir" && tar -xf -)
  else
    (cd "$src" && tar -cf - --exclude=__pycache__ .) | (cd "$TARGET/$dir" && tar -xf -)
  fi
done
[ -f "$MANIFEST" ] && cp "$MANIFEST" "$MANIFEST.old"
mv "$MANIFEST.new" "$MANIFEST"
# A hook this repo stopped shipping is still wired in every project deployed
# with it; its entry now points at a deleted script. Say how to clean that up.
if [ -f "$MANIFEST.old" ]; then
  retired=$(grep '^hooks/[^/]*$' "$MANIFEST.old" | grep -vxF -f "$MANIFEST" || true)
  rm -f "$MANIFEST.old"
  if [ -n "$retired" ]; then
    echo "  ! retired hooks removed: $(echo "$retired" | sed 's|^hooks/||' | tr '\n' ' ')"
    echo "    Projects that wired them: run /init-project --update (or init.sh) to prune the entries."
  fi
fi
# Removing a skill's files leaves its directory behind, and an empty
# ~/.claude/skills/<name>/ still shows up in the skill listing as a phantom.
# Prune only the directories that removing our own files emptied — an empty
# directory the user made (a skill in progress) is theirs — and never climb
# above the top-level tree (skills/, agents/, ...).
sort -ru "$EMPTIED" | while IFS= read -r d; do
  while [ "${d#*/}" != "$d" ]; do
    rmdir "$TARGET/$d" 2>/dev/null || break
    d="$(dirname "$d")"
  done
done
echo "  - central hooks/agents/skills/rules/output-styles installed (.sh + .py hooks)"

# --- Central settings.json: MERGE into the user's, do not clobber ------------
# Three classes of key, and the distinction is the whole point:
#   OWNED  - the deterministic guarantees (permissions/hooks/attribution).
#            Overwritten on every install; a user edit to these is drift.
#   SEEDED - defaults worth having on a fresh machine but which the user may
#            legitimately change (outputStyle, /rewind snapshots). Written ONLY
#            when absent, so `git pull && ./install.sh` never reverts a choice
#            made with /config. Owning them would violate the installer's
#            contract that it never touches user content (CLAUDE.md §3).
#   everything else - the user's, preserved untouched.
# install.ps1 rebuilds this object key by key, so both lists live there too;
# check.py asserts all three sites agree.
python3 - "$SCRIPT_DIR/global/.claude/settings.json" "$TARGET/settings.json" <<'PY'
import json, os, sys
src_path, dst_path = sys.argv[1], sys.argv[2]
with open(src_path) as f:
    src = json.load(f)
for k in [k for k in src if k.startswith("_")]:
    src.pop(k)
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
OWNED = ("permissions", "hooks", "attribution")
SEEDED = ("outputStyle", "fileCheckpointingEnabled", "statusLine")
replaced = [k for k in OWNED if k in dst and k in src and dst[k] != src[k]]
if replaced:
    # The owned keys are the deterministic guarantee, so they are replaced —
    # but a deny rule or a hook the user added there must never vanish
    # without a trace. Keep the whole previous file next to it.
    import shutil, time
    backup = "%s.bak-%s" % (dst_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(dst_path, backup)
    sys.stderr.write(
        "  ! %s was replaced in ~/.claude/settings.json (dotclaude owns it); your previous\n"
        "    file is saved at %s — move personal rules or hooks to a project's\n"
        "    .claude/settings.json or settings.local.json, which merge on top.\n"
        % (", ".join(replaced), backup))
for key in OWNED:
    if key in src:
        dst[key] = src[key]
# After an unparseable settings.json dst is empty, so everything seeds — the
# user's old values are unrecoverable anyway and the backup holds them.
# A status line an earlier install seeded points at the retired statusline.sh;
# that value is ours to repair. Any other value is the user's choice and stays.
LEGACY_STATUSLINE = ('"$HOME"/.claude/hooks/statusline.sh',)
if (dst.get("statusLine") or {}).get("command") in LEGACY_STATUSLINE:
    del dst["statusLine"]
seeded = [k for k in SEEDED if k in src and k not in dst]
for key in seeded:
    dst[key] = src[key]
with open(dst_path, "w") as f:
    json.dump(dst, f, indent=2)
    f.write("\n")
note = " seeded %s;" % ", ".join(seeded) if seeded else ""
print("  - ~/.claude/settings.json merged (permissions, hooks, attribution set to dotclaude's;%s "
      "your other keys kept)" % note)
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
