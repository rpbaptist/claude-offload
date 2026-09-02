# claude-offload

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
git clone https://github.com/rpbaptist/claude-offload ~/code/claude-offload
cd ~/code/claude-offload
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
any stale `PostToolUse` registration left by an install from before the
[SubagentStop redesign](https://github.com/rpbaptist/claude-offload/issues/2))
and appends `claude/delegation-policy.md` to `~/.claude/CLAUDE.md`.

Restart Claude Code afterwards.

## Verifying the install

Hooks, agents and `CLAUDE.md` are only read at session start, so none of this
can be verified from the session that ran `install.sh` — **restart Claude
Code first.** Everything above was already checked at install time (the CLI,
its guards, the hook script's branching, install idempotency); what's left is
whether the three pieces are actually wired into a live session, and whether
delegation behaves as intended once it runs for real. Work through these in
order — each builds on the last.

### 1. The agent is registered

Run `/agents`. Expect `local-exec` in the list.

*If missing:* check `~/.claude/agents/local-exec.md` resolves —
`readlink -f ~/.claude/agents/local-exec.md`. A broken symlink means the repo
moved after install; rerun `./install.sh`.

### 2. The hook is silent for other subagents

Ask for anything that uses a different subagent — "explore how X works" — and
confirm **no** verification-required message appears in that subagent's
transcript.

*If a message appears:* the `matcher: "local-exec"` entry for `SubagentStop`
in `~/.claude/settings.json` isn't scoped correctly, or points at the wrong
`agent_type`. Check the entry's `matcher` field.

### 3. The hook fires for local-exec, and only after ollama-gen

In a git repo with a **clean tree**, explicitly ask: *"use local-exec to write a
`greet(name)` utility in `src/greet.py`"*.

Expand local-exec's own transcript. Expect: an `ollama-gen` call, then (if
local-exec tries to stop without verifying) a blocked-stop message telling it
to run the project's lint/typecheck/build/test — and then local-exec actually
running something and succeeding before it's allowed to finish. This is
enforced on local-exec itself, not on the orchestrating Claude — see
["The three pieces"](#the-three-pieces) below for why.

*If nothing appears, or local-exec is never blocked even without verifying:*
confirm the `SubagentStop`/`local-exec` entry is in `~/.claude/settings.json`
and that the command path is executable. Test it standalone against a fixture
transcript:

```sh
cat > /tmp/local-exec-review-test.jsonl <<'EOF'
{"message":{"content":[{"type":"tool_use","id":"tu1","name":"Bash","input":{"command":"ollama-gen --task \"greet util\" --out src/greet.py"}}]}}
{"message":{"content":[{"type":"tool_result","tool_use_id":"tu1","is_error":false,"content":"Created src/greet.py (5 lines)."}]}}
EOF
echo '{"transcript_path":"/tmp/local-exec-review-test.jsonl"}' \
  | ~/.claude/hooks/local-exec-review.py; echo "exit=$?"
```

Expect the "haven't verified" message on stderr and `exit=2`. Append a
successful `Bash` tool_use/tool_result pair (any command, exit 0) to the
fixture after the `ollama-gen` pair and re-run — expect `exit=0`.

*If the message appears but local-exec ignores it and stops anyway:* that's
the interesting failure. Note it — this enforcement is the whole basis for
trusting a model this small with unattended file writes.

### 4. Context files are not read into context — the important one

Ask for something that needs an existing file as reference: *"use local-exec to
write a test module for `src/greet.py`"*.

In the transcript, expand the subagent's turns. Expect a `Bash` call containing
`--context src/greet.py`. Expect **no** `Read` call on `src/greet.py`.

*If it read the file first:* the largest saving in the design is gone — the file
body entered context anyway, and you paid for the delegation on top. Sharpen
step 1 of `agents/local-exec.md` and re-test. This is the single most likely
place for the setup to quietly fail to pay off.

### 5. Auto-routing works without naming the agent

In a fresh session, ask for something qualifying without mentioning local-exec:
*"add a DTO for the user endpoint"*.

Expect a one-line announcement — *"Delegating the user DTO to local-exec"* —
followed by the subagent call (`Agent` in this harness; see
[#1](https://github.com/rpbaptist/claude-offload/issues/1)).

*If it does the work itself:* the `CLAUDE.md` policy isn't landing. Check it
survived (`grep -n "Delegating mechanical" ~/.claude/CLAUDE.md`). If present,
the routing prose is losing against the rest of the context; make the delegate /
don't-delegate lists more concrete.

*If the announcement is missing but delegation happens:* acceptable but not what
was asked for — you lose the chance to redirect before the work happens.

### 6. Out-of-scope work is not delegated

Ask for something that should stay with Claude: a refactor touching four or five
files, or a fix to subtle logic.

Expect no delegation.

*If it delegates anyway:* tighten the "Do not delegate" list. Over-delegation is
the expensive failure — it produces plausible code that costs a full review to
reject.

### 7. Does it actually save anything

After a week of real use, sanity-check the premise rather than assuming it.

Every `ollama-gen` call — including retries and empty-output failures — is
logged to `$OLLAMA_GEN_LOG` (default `~/.claude/ollama-gen-usage.jsonl`).
Run:

```sh
jq -s 'map(select(.empty_output)) | length' "$OLLAMA_GEN_LOG"
```

against

```sh
jq -s 'map(.estimated_tokens_avoided) | add' "$OLLAMA_GEN_LOG"
```

A high empty-output/retry count relative to the number of distinct `out`
paths is the failure mode to watch for: a bad generation costs two retries
plus a review and ends up more expensive than writing it once. If that's
common, narrow what gets delegated — the fix is scope, not prompt
engineering. See ["Usage tracking"](#usage-tracking) below for the full
schema and what "tokens avoided" does and doesn't account for — it's an
estimate, not a measured net saving, so treat it as a signal, not a final
number. Comparing a delegated task against writing the same thing directly
by hand remains the tighter (but manual) check if you want a real
counterfactual.

Also confirm `--context` files aren't blowing the model's window on larger
files; whole-file generation degrades past a few hundred lines.

## Rollback

```sh
rm ~/.local/bin/ollama-gen \
   ~/.claude/agents/local-exec.md \
   ~/.claude/hooks/local-exec-review.py
mv ~/.claude/settings.json.bak ~/.claude/settings.json
mv ~/.claude/CLAUDE.md.bak ~/.claude/CLAUDE.md
```

Then restart. Note the `.bak` files are from the **first** install run only —
later runs skip the backup when nothing changes, so they reflect pre-install
state. The usage log at `$OLLAMA_GEN_LOG` is just data — rollback leaves it in
place.

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
[#2](https://github.com/rpbaptist/claude-offload/issues/2) — subagent
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
["Does it actually save anything"](#7-does-it-actually-save-anything) above).
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
