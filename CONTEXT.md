# ollama-subagent

Routes mechanical code generation from Claude Code to a local Ollama model
(via the `local-exec` subagent and `ollama-gen` CLI), and enforces that the
generated output gets checked before it's treated as done.

## Language

**Verification**:
An automated check (lint/typecheck/build/test) that local-exec runs on its
own `ollama-gen` output, enforced by the `SubagentStop` hook
(`hooks/local-exec-review.py`) — local-exec cannot stop without it. Catches
mechanical breakage only: syntax errors, failing builds. Cannot catch a
plausible-looking wrong approach.
_Avoid_: Review (see below), validation, checking.

**Review**:
A capable model examining local-exec's output for correctness and judgment —
approach, security, whether it does the right thing, not just whether it
runs. Prompt-level only (`claude/delegation-policy.md`); no hook can enforce
this for an async subagent, since no hook fires in the orchestrator's own
context when an async subagent's result arrives (see
[ADR-0001](docs/adr/0001-subagentstop-self-verification.md)).
_Avoid_: Verification (distinct concept, see above).
