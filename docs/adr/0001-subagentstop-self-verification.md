# SubagentStop enforces local-exec self-verification, not orchestrator review

`hooks/local-exec-review.py` originally used `PostToolUse` + exit-code-2 to
force the orchestrating Claude to review local-exec's output before treating
delegated work as done. That broke ([#2](https://github.com/rpbaptist/claude-offload/issues/2)):
subagent launches are async in this harness, so `PostToolUse` fires 2ms after
launch, before local-exec has written anything — and never fires again on
completion.

`SubagentStop` fires on actual completion, but its exit-code-2 block only
reaches the subagent trying to stop, never the parent session — confirmed via
Claude Code's docs, and already noted in this repo's own `README.md` when the
original design was built. No hook fires in the parent's context when an
async subagent's result arrives. We also checked whether local-exec could be
forced to run synchronously (which would keep the original design valid) —
no per-agent or per-invocation way to do that exists; the only options are a
non-deterministic natural-language request or a global env var that would
kill background execution for every subagent in the session, not just this
one.

**Decision:** redefine the guarantee. `SubagentStop` now enforces that
local-exec verifies its own `ollama-gen` output (a successful command after
the call) before it's allowed to stop. This is real, hook-enforced mechanical
self-verification — not the judgment-level review the original design wanted
and cannot get. The orchestrator reviewing the diff itself remains a
prompt-level ask (`claude/delegation-policy.md`), not hook-enforced.

**Considered and rejected:**
- A soft signal instead (`SubagentStop` forcing an "UNREVIEWED" marker into
  local-exec's final report, trusting the orchestrator to notice it) — no
  stronger than the prompt-level ask already in place.
- The hook running its own lint/build command directly, instead of checking
  the transcript for one — rejected because local-exec is a generic agent
  installed across arbitrary target repos with no fixed lint/build command;
  local-exec's own project-aware judgment (already prompted for in
  `agents/local-exec.md` step 5) is more reliable than a hook guessing.
