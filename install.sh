#!/usr/bin/env bash
# Install ollama-subagent into ~/.claude and ~/.local/bin. Idempotent.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
BIN_DIR="$HOME/.local/bin"
SETTINGS="$CLAUDE_DIR/settings.json"
CLAUDE_MD="$CLAUDE_DIR/CLAUDE.md"
POLICY="$REPO/claude/delegation-policy.md"
POLICY_HEADING="## Delegating mechanical work to the local model"

info() { printf '  %s\n' "$1"; }

chmod +x "$REPO/bin/ollama-gen" "$REPO/hooks/local-exec-review.py"

mkdir -p "$BIN_DIR" "$CLAUDE_DIR/agents" "$CLAUDE_DIR/hooks"

link() {
  local src="$1" dst="$2"
  if [ -L "$dst" ] && [ "$(readlink -f "$dst")" = "$(readlink -f "$src")" ]; then
    info "ok      $dst"
  elif [ -e "$dst" ] && [ ! -L "$dst" ]; then
    echo "  REFUSING: $dst exists and is not a symlink. Move it aside." >&2
    exit 1
  else
    ln -sfn "$src" "$dst"
    info "linked  $dst"
  fi
}

echo "Linking:"
link "$REPO/bin/ollama-gen"              "$BIN_DIR/ollama-gen"
link "$REPO/agents/local-exec.md"        "$CLAUDE_DIR/agents/local-exec.md"
link "$REPO/hooks/local-exec-review.py"  "$CLAUDE_DIR/hooks/local-exec-review.py"

echo "Settings:"
HOOK_CMD="$CLAUDE_DIR/hooks/local-exec-review.py" \
SETTINGS_PATH="$SETTINGS" \
python3 - <<'PY'
import json, os, shutil, sys

path = os.environ["SETTINGS_PATH"]
cmd = os.environ["HOOK_CMD"]

data = {}
if os.path.exists(path):
    with open(path) as f:
        data = json.load(f)

hooks = data.setdefault("hooks", {})
post = hooks.setdefault("PostToolUse", [])

for entry in post:
    for h in entry.get("hooks", []):
        if h.get("command") == cmd:
            if entry.get("matcher") == "*":
                print("  ok      PostToolUse hook already present")
            else:
                shutil.copy2(path, path + ".bak")
                print(f"  backup  {path}.bak")
                entry["matcher"] = "*"
                with open(path, "w") as f:
                    json.dump(data, f, indent=2)
                    f.write("\n")
                print("  upgraded PostToolUse matcher -> *")
            sys.exit(0)

if os.path.exists(path):
    shutil.copy2(path, path + ".bak")
    print(f"  backup  {path}.bak")

post.append({
    "matcher": "*",
    "hooks": [{"type": "command", "command": cmd}],
})

with open(path, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
print("  added   PostToolUse hook")
PY

echo "CLAUDE.md:"
if [ -f "$CLAUDE_MD" ] && grep -qF "$POLICY_HEADING" "$CLAUDE_MD"; then
  info "ok      delegation policy already present"
else
  if [ -f "$CLAUDE_MD" ]; then
    cp -p "$CLAUDE_MD" "$CLAUDE_MD.bak"
    info "backup  $CLAUDE_MD.bak"
    printf '\n' >>"$CLAUDE_MD"
  fi
  cat "$POLICY" >>"$CLAUDE_MD"
  info "added   delegation policy"
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "  WARNING: $BIN_DIR is not on PATH" >&2 ;;
esac

if ! command -v ollama >/dev/null 2>&1; then
  echo "  WARNING: ollama not found on PATH" >&2
fi

echo
echo "Done. Restart Claude Code to pick up the new hook, agent, and CLAUDE.md."
