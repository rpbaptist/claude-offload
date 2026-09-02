#!/usr/bin/env python3
"""PostToolUse hook: force review of local-exec output in the parent session.

PostToolUse ignores `decision` and `additionalContext`, but exit code 2 shows
stderr to Claude. That is the injection channel used here.
"""
import json
import subprocess
import sys

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)

if (payload.get("tool_input") or {}).get("subagent_type") != "local-exec":
    sys.exit(0)

cwd = payload.get("cwd") or "."
try:
    in_repo = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True).stdout.strip() == "true"
except Exception:
    in_repo = False

head = ("local-exec has finished. Its output came from a 20B local model and is "
        "NOT yet reviewed. ")
if in_repo:
    tail = ("Run `git diff` (and `git status` for new files) and review the "
            "changes for correctness before treating this task as done. The "
            "diff may also contain pre-existing uncommitted work — review only "
            "what local-exec reported writing.")
else:
    tail = ("This directory is not a git repository, so read the files "
            "local-exec reported writing and review them for correctness "
            "before treating this task as done.")

print(head + tail, file=sys.stderr)
sys.exit(2)
