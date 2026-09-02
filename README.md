# ollama-subagent

Route mechanical code generation from Claude Code to a local Ollama model, and
force Claude to review the result.

Claude Code stays on planning, architecture and review. Boilerplate — DTOs,
CRUD handlers, config files, test stubs — gets written by a local model for
free.

## Why this shape

Claude Code has **no per-subagent backend switching**. Subagent `model:`
frontmatter accepts only Claude aliases, and every subagent shares the main
session's backend. A subagent that literally runs on a local model is not
possible.

What *is* possible: a CLI wrapper around Ollama, invoked via the Bash tool by a
cheap Haiku-backed subagent.

## Where the token savings come from

1. **Context files never enter Claude's context.** `ollama-gen` takes file
   *paths* and reads them from disk itself. Claude passes a path string; Ollama
   consumes the file body for free. This is the largest win.
2. **File bodies are generated locally.** Generated code is the most expensive
   kind of token — output tokens — and it comes back only as
   `Created src/foo.py (47 lines).`

You still pay for the task description, the `Task` call and its summary, and the
review, where the file is read back as input tokens. That last one is
deliberate. The trade is *expensive output tokens replaced by cheaper input
tokens*, not "Claude never sees the code."

This does **not** pay off on small edits, where writing a precise task
description costs more than making the edit. The subagent short-circuits those.

## Install

Requires Python 3 (stdlib only), `git`, and a running Ollama.

```sh
git clone https://github.com/rpbaptist/ollama-subagent ~/code/ollama-subagent
cd ~/code/ollama-subagent
./install.sh
```

`install.sh` is idempotent. It symlinks — so edits in the repo take effect
immediately — and backs up anything it modifies:

| Link | Target |
| --- | --- |
| `~/.local/bin/ollama-gen` | `bin/ollama-gen` |
| `~/.claude/agents/local-exec.md` | `agents/local-exec.md` |
| `~/.claude/hooks/local-exec-review.py` | `hooks/local-exec-review.py` |

It also merges a `PostToolUse` hook into `~/.claude/settings.json` (backing it
up to `settings.json.bak`, leaving other hooks untouched) and appends
`claude/delegation-policy.md` to `~/.claude/CLAUDE.md`.

Restart Claude Code afterwards.

## The three pieces

**`bin/ollama-gen`** — the wrapper. Takes a task and a target path, POSTs to
Ollama, writes the file, prints a one-line summary.

```sh
ollama-gen --task "a UserDTO dataclass with id, email, created_at; frozen" \
           --out src/dto/user.py \
           --context src/models/user.py
# Created src/dto/user.py (18 lines).
```

| Flag | |
| --- | --- |
| `--task` | what to generate (required) |
| `--out` | target path (required) |
| `--context` | file path passed to the model as context; repeatable |
| `--force` | required to overwrite an existing file |
| `--timeout` | seconds, default 300 |

Guards: refuses to overwrite without `--force`, refuses to write outside the
current directory, refuses empty model output, and strips markdown fences if the
model emits them anyway.

**`agents/local-exec.md`** — a Haiku subagent that calls `ollama-gen`, runs
lint/build on each result, and retries with a clearer task description on
failure. It has no `Write` tool, so file creation must go through the local
model. All of this happens in an isolated context, so a multi-file batch's
generate/lint/retry turns never touch your main session.

**`hooks/local-exec-review.py`** — a `PostToolUse` hook (matcher `"*"`, so it
runs after every tool call) that filters in-script on
`tool_input.subagent_type == "local-exec"`, rather than matching on the
subagent-launching tool's own name — that name has already changed once
across harness versions (`Task` → `Agent`; see
[#1](https://github.com/rpbaptist/ollama-subagent/issues/1)). When
`local-exec` returns, it tells the orchestrator to review the output before
treating the work as done. It exits silently for every other tool call.

`PostToolUse` ignores `decision` and `additionalContext`, but exit code 2 shows
stderr to Claude — that's the injection channel. `SubagentStop` can't be used
here: it cannot reach the parent session.

## Configuration

| Env var | Default |
| --- | --- |
| `OLLAMA_GEN_MODEL` | `gpt-oss-20b-32k:latest` |
| `OLLAMA_HOST_URL` | `http://localhost:11434` |
| `CLAUDE_CONFIG_DIR` | `~/.claude` (install only) |

## What delegates well

**Yes:** boilerplate (CRUD handlers, DTOs, schemas, config files), test stubs
from clear signatures, single-file utilities with a clear spec, well-specified
pseudocode → code, docstrings, mechanical repetitive edits.

**No:** anything spanning multiple files, architecture or design decisions,
subtle logic, non-trivial refactors, security-sensitive code. A 20B model
produces plausible-looking wrong output with no awareness that it's wrong. The
review step exists for exactly this.

A whole plan cannot be handed over. Planning stays with Claude, which decomposes
it into single-file, unambiguous tasks; only those go local.

## Known limitations

- **Dirty-tree conflation.** `git diff` shows the local model's writes mixed
  with your uncommitted work. Commit before delegating.
- **File-size ceiling.** Generation is whole-file, never patches — a 20B model
  can't reliably emit applyable diffs. Expect degradation past a few hundred
  lines.
- **Model-swap latency.** With `OLLAMA_MAX_LOADED_MODELS=1`, the first call
  pays a model load if something else is resident.
- **Prose routing heuristic.** The CLAUDE.md policy is judgement, not a rule
  engine, which is why it asks Claude to announce delegation before doing it.

## License

MIT
