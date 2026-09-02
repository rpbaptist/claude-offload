## Delegating mechanical work to the local model

A `local-exec` subagent delegates code generation to a local Ollama model
(gpt-oss-20b) to save API tokens. Route qualifying work to it automatically —
do not wait to be asked — but state one line first, e.g. "Delegating the 3 DTO
files to local-exec", before invoking it, so the routing decision can be
redirected before the work happens.

Delegate: boilerplate (CRUD handlers, DTOs, schemas, config files), test stubs
from clear signatures, single-file utilities with a clear spec, docstrings,
well-specified pseudocode → code, mechanical repetitive edits.

Do not delegate: anything spanning multiple files as one coherent change,
architecture or design decisions, subtle logic or debugging, non-trivial
refactors, security-sensitive code, or any task where writing a precise
description would cost more than making the edit directly.

A hook forces local-exec to verify its own output (run the project's
lint/typecheck/build/test successfully) before it's allowed to stop — that
part is mandatory and enforced. It only catches mechanical breakage, though,
not a plausible-looking wrong approach. The output is from a 20B model, so
still look it over yourself before treating the task as done.
