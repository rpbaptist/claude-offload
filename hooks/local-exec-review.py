#!/usr/bin/env python3
"""SubagentStop hook: force local-exec to verify its own ollama-gen output.

SubagentStop can only block the subagent that is trying to stop -- it cannot
reach the parent session (see README.md). So this does not force the
orchestrator to review anything; it forces local-exec itself to run a
successful command after its last ollama-gen call before it's allowed to
stop. Exit code 2 on SubagentStop blocks the stop and feeds stderr back into
local-exec's own turn -- that is the injection channel used here.

The matcher for this hook (agent_type == "local-exec") lives in
settings.json, not here -- SubagentStop supports matching on agent_type
declaratively, so there's no tool-name or subagent-type filtering to do
in-script.
"""
import json
import re
import sys

OLLAMA_GEN_RE = re.compile(r"(?:^|[\s;&|])ollama-gen\s+--")

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)

transcript_path = payload.get("transcript_path")
if not transcript_path:
    sys.exit(0)

try:
    with open(transcript_path) as f:
        lines = f.readlines()
except OSError:
    sys.exit(0)

entries = []
for line in lines:
    line = line.strip()
    if not line:
        continue
    try:
        entries.append(json.loads(line))
    except ValueError:
        continue


def bash_calls(entries):
    """Yield (command, tool_use_id) for every Bash tool_use, in order."""
    for entry in entries:
        message = entry.get("message") or {}
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use" \
                    and block.get("name") == "Bash":
                command = (block.get("input") or {}).get("command") or ""
                yield command, block.get("id")


def tool_result_exit_code(entries, tool_use_id):
    """Find the tool_result for tool_use_id and return its exit code, or None."""
    for entry in entries:
        message = entry.get("message") or {}
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_result" \
                    and block.get("tool_use_id") == tool_use_id:
                if block.get("is_error"):
                    return 1
                return 0
    return None


calls = list(bash_calls(entries))

last_gen_index = None
for i, (command, _tool_use_id) in enumerate(calls):
    if OLLAMA_GEN_RE.search(command):
        last_gen_index = i

if last_gen_index is None:
    # No ollama-gen call this turn -- nothing to verify (trivial direct
    # edits are exempt).
    sys.exit(0)

verified = False
failure_command = None
failure_code = None
for command, tool_use_id in calls[last_gen_index + 1:]:
    code = tool_result_exit_code(entries, tool_use_id)
    if code is None:
        continue
    if code == 0:
        verified = True
        break
    else:
        failure_command, failure_code = command, code

if verified:
    sys.exit(0)

if failure_command is not None:
    detail = (f"Your last verification attempt (`{failure_command}`) failed "
               f"(exit {failure_code}). Fix the issue and verify again.")
else:
    detail = ("Run the project's lint/typecheck/build/test command on the "
               "file(s) you just generated and confirm it passes.")

print(
    "You called ollama-gen but haven't verified the result yet. " + detail +
    " Do not stop until verification succeeds.",
    file=sys.stderr,
)
sys.exit(2)
