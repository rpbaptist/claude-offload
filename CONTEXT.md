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

**Local cost**:
The real token counts (`prompt_eval_count`, `eval_count`) Ollama reports for
a single `ollama-gen` call — what delegation actually cost on the local
model, regardless of whether the output was usable. Measured, not estimated.
_Avoid_: Tokens avoided (see below, a different and estimated number),
tokens saved.

**Tokens avoided**:
An estimate of the input and output tokens Claude did not spend by
delegating a generation — the context files `ollama-gen` read directly and
the file it wrote, converted from bytes at a fixed heuristic ratio. Not
netted against the task-description or review-read overhead Claude still
pays, since neither is tracked. A heuristic, not a measurement.
_Avoid_: Tokens saved (implies a measured net figure this project cannot
produce), local cost (see above, a different and measured number).
