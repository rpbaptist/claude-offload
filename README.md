# ollama-subagent

Route mechanical code generation from Claude Code to a local Ollama model, and
force that output to be verified before it's handed back.

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

## Where the savings come from

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

This is now measurable, not just architectural — see
[Usage tracking](#usage-tracking) below.

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

It also merges a `SubagentStop` hook into `~/.claude/settings.json` (backing
it up to `settings.json.bak`, leaving other hooks untouched — and removing
any stale `PostToolUse` registration from a pre-#2 install, see
["Upgrading from a pre-#2 install"](POST-INSTALL.md#upgrading-from-a-pre-2-install)
in `POST-INSTALL.md`) and appends `claude/delegation-policy.md` to
`~/.claude/CLAUDE.md`.

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

**`hooks/local-exec-review.py`** — a `SubagentStop` hook (matcher
`"local-exec"`, matched declaratively on `agent_type` — no in-script
filtering needed) that scans local-exec's own transcript for its last
`ollama-gen` call and blocks it from stopping until a later Bash command
after that call exits 0.

This is a narrower guarantee than it sounds: `SubagentStop`'s exit-code-2
block only reaches the subagent that's trying to stop, never the parent
session, so this cannot force the orchestrator to review anything (see
[#2](https://github.com/rpbaptist/ollama-subagent/issues/2) — subagent
launches are async in this harness, and no hook fires in the parent's
context when an async subagent's result actually arrives). What it *can*
enforce is that local-exec verifies its own output — runs the project's
lint/typecheck/build/test and gets a clean exit — before it's allowed to
stop. That's mechanical self-verification, not judgment-level review; the
orchestrator is still asked (in `claude/delegation-policy.md`, prompt-level
only) to look the output over itself. See
[`docs/adr/0001-subagentstop-self-verification.md`](docs/adr/0001-subagentstop-self-verification.md)
for why.

Trivial single-file edits local-exec makes directly (no `ollama-gen` call —
see step 2 of `agents/local-exec.md`) are exempt; the hook only blocks after
an actual `ollama-gen` invocation.

## Configuration

| Env var | Default |
| --- | --- |
| `OLLAMA_GEN_MODEL` | `gpt-oss-20b-32k:latest` |
| `OLLAMA_HOST_URL` | `http://localhost:11434` |
| `CLAUDE_CONFIG_DIR` | `~/.claude` |
| `OLLAMA_GEN_LOG` | `$CLAUDE_CONFIG_DIR/ollama-gen-usage.jsonl` |

## Usage tracking

Every `ollama-gen` call that reaches Ollama appends one line to
`$OLLAMA_GEN_LOG` — including retries and calls where the model returned
empty output. A failed retry still burned real local compute; hiding it
would hide the exact failure mode worth watching for (see
["Does it actually save anything"](POST-INSTALL.md#7-does-it-actually-save-anything)
in `POST-INSTALL.md`).
Calls that fail before reaching Ollama (missing `--context` file, refusing
to overwrite without `--force`) log nothing — no API call happened.

There's no counterfactual run to diff against — Claude never generates the
same file itself to compare — so "tokens saved" isn't a fact this tool can
produce. Each line reports two differently-certain numbers instead, and they
are never blended into one figure:

- **Local cost (measured)** — `prompt_eval_count` and `eval_count`, Ollama's
  own real token counts for the call.
- **Tokens avoided (estimated)** — `(context_bytes + generated_bytes) / 4`, a
  rough heuristic for what Claude would have spent reading the context files
  and writing the output itself, had it done the work directly. This is
  *not* netted against the task description, the `Task` call, or the
  review-read — none of those are tracked, and folding them in would imply
  more precision than the heuristic has.

```json
{"ts": "2026-09-02T21:14:03Z", "model": "gpt-oss-20b-32k:latest",
 "out": "src/dto/user.py", "context_files": ["src/models/user.py"],
 "context_bytes": 812, "generated_bytes": 431, "empty_output": false,
 "prompt_eval_count": 946, "eval_count": 118,
 "estimated_tokens_avoided": 310}
```

```sh
# Tokens avoided, all time
jq -s 'map(.estimated_tokens_avoided) | add' "$OLLAMA_GEN_LOG"

# Real local cost, all time
jq -s 'map((.prompt_eval_count // 0) + (.eval_count // 0)) | add' "$OLLAMA_GEN_LOG"

# Wasted (empty-output) calls
jq -s 'map(select(.empty_output)) | length' "$OLLAMA_GEN_LOG"
```

## What delegates well

**Yes:** boilerplate (CRUD handlers, DTOs, schemas, config files), test stubs
from clear signatures, single-file utilities with a clear spec, well-specified
pseudocode → code, docstrings, mechanical repetitive edits.

**No:** anything spanning multiple files, architecture or design decisions,
subtle logic, non-trivial refactors, security-sensitive code. A 20B model
produces plausible-looking wrong output with no awareness that it's wrong.
The verification step catches mechanical breakage (syntax errors, failing
lint/build/tests); it can't catch a plausible-looking wrong approach. That's
still on whoever reviews the diff.

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
