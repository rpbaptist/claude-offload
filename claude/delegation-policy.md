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

After local-exec returns, a hook will require you to review its output. That
review is mandatory: the output is from a 20B model and is frequently
plausible-looking but wrong.
