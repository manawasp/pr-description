#!/usr/bin/env bash
# Links the skill and the guard into ~/.claude, registers the hook, runs the tests.
# Safe to rerun: existing links are kept, anything else in the way is moved to ~/.claude/backups.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE="${CLAUDE_HOME:-$HOME/.claude}"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$CLAUDE/skills" "$CLAUDE/hooks" "$CLAUDE/backups"

link() {
  local target=$1 path=$2
  if [ -L "$path" ] && [ "$(readlink "$path")" = "$target" ]; then
    echo "ok        $path"
    return
  fi
  if [ -e "$path" ] || [ -L "$path" ]; then
    mv "$path" "$CLAUDE/backups/$(basename "$path").$STAMP"
    echo "backed up $path"
  fi
  ln -s "$target" "$path"
  echo "linked    $path -> $target"
}

link "$REPO/skill" "$CLAUDE/skills/pr-description"
link "$REPO/hooks/pr-body-guard.py" "$CLAUDE/hooks/pr-body-guard.py"

python3 - "$CLAUDE" "$STAMP" <<'PY'
import json, os, shutil, sys
claude, stamp = sys.argv[1], sys.argv[2]
path = os.path.join(claude, "settings.json")
cmd = "python3 ~/.claude/hooks/pr-body-guard.py"
settings = {}
if os.path.exists(path):
    shutil.copy(path, os.path.join(claude, "backups", f"settings.json.{stamp}"))
    with open(path, encoding="utf-8") as fh:
        settings = json.load(fh)
pre = settings.setdefault("hooks", {}).setdefault("PreToolUse", [])
if any(h.get("command") == cmd for group in pre for h in group.get("hooks", [])):
    print("ok        hook already registered in settings.json")
else:
    pre.append({"matcher": "Bash", "hooks": [{"type": "command", "command": cmd, "timeout": 10, "statusMessage": "Checking PR body"}]})
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("added     hook to settings.json")
PY

python3 "$REPO/hooks/test_pr_body_guard.py" 2>&1 | tail -1
echo "Installed. A running Claude Code session picks the hook up after /hooks; a new session has it from the start."
