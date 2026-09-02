# Post-install checks

Hooks, agents and `CLAUDE.md` are read at session start, so none of this can be
verified from the session that ran `install.sh`. **Restart Claude Code first.**

Everything in `README.md` was verified at install time — the CLI, its guards,
the hook script's branching, and install idempotency. What remains is whether
the three pieces are actually wired into a live session, and whether the
delegation behaves as intended once it runs for real.

Work through these in order; each builds on the last.

---

## 1. The agent is registered

Run `/agents`. Expect `local-exec` in the list.

*If missing:* check `~/.claude/agents/local-exec.md` resolves —
`readlink -f ~/.claude/agents/local-exec.md`. A broken symlink means the repo
moved after install; rerun `./install.sh`.

## 2. The hook is silent for other subagents

Ask for anything that uses a different subagent — "explore how X works" — and
confirm **no** verification-required message appears in that subagent's
transcript.

*If a message appears:* the `matcher: "local-exec"` entry for `SubagentStop`
in `~/.claude/settings.json` isn't scoped correctly, or points at the wrong
`agent_type`. Check the entry's `matcher` field.

## 3. The hook fires for local-exec, and only after ollama-gen

In a git repo with a **clean tree**, explicitly ask: *"use local-exec to write a
`greet(name)` utility in `src/greet.py`"*.

Expand local-exec's own transcript. Expect: an `ollama-gen` call, then (if
local-exec tries to stop without verifying) a blocked-stop message telling it
to run the project's lint/typecheck/build/test — and then local-exec actually
running something and succeeding before it's allowed to finish. This is
enforced on local-exec itself, not on the orchestrating Claude — see
`README.md`'s description of `hooks/local-exec-review.py` for why.

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

## 4. Context files are not read into context — the important one

Ask for something that needs an existing file as reference: *"use local-exec to
write a test module for `src/greet.py`"*.

In the transcript, expand the subagent's turns. Expect a `Bash` call containing
`--context src/greet.py`. Expect **no** `Read` call on `src/greet.py`.

*If it read the file first:* the largest saving in the design is gone — the file
body entered context anyway, and you paid for the delegation on top. Sharpen
step 1 of `agents/local-exec.md` and re-test. This is the single most likely
place for the setup to quietly fail to pay off.

## 5. Auto-routing works without naming the agent

In a fresh session, ask for something qualifying without mentioning local-exec:
*"add a DTO for the user endpoint"*.

Expect a one-line announcement — *"Delegating the user DTO to local-exec"* —
followed by the subagent call (`Agent` in this harness; see
[#1](https://github.com/rpbaptist/ollama-subagent/issues/1)).

*If it does the work itself:* the `CLAUDE.md` policy isn't landing. Check it
survived (`grep -n "Delegating mechanical" ~/.claude/CLAUDE.md`). If present,
the routing prose is losing against the rest of the context; make the delegate /
don't-delegate lists more concrete.

*If the announcement is missing but delegation happens:* acceptable but not what
was asked for — you lose the chance to redirect before the work happens.

## 6. Out-of-scope work is not delegated

Ask for something that should stay with Claude: a refactor touching four or five
files, or a fix to subtle logic.

Expect no delegation.

*If it delegates anyway:* tighten the "Do not delegate" list. Over-delegation is
the expensive failure — it produces plausible code that costs a full review to
reject.

## 7. Does it actually save anything

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
engineering. See `README.md`'s ["Usage tracking"](README.md#usage-tracking)
for the full schema and what "tokens avoided" does and doesn't account for
— it's an estimate, not a measured net saving, so treat it as a signal, not
a final number. Comparing a delegated task against writing the same thing
directly by hand remains the tighter (but manual) check if you want a real
counterfactual.

Also confirm `--context` files aren't blowing the model's window on larger
files; whole-file generation degrades past a few hundred lines.

---

## Upgrading from a pre-#2 install

If `~/.claude/settings.json` still has a `PostToolUse` entry for
`hooks/local-exec-review.py` (from an install before the
[SubagentStop redesign](https://github.com/rpbaptist/ollama-subagent/issues/2)
— including the brief `Task`→`Agent` matcher fix in
[#1](https://github.com/rpbaptist/ollama-subagent/issues/1)), that design
never saw local-exec's real output: subagent launches are async in this
harness, so `PostToolUse` fired at launch, before local-exec had written
anything. Rerun `./install.sh`: it detects the stale `PostToolUse` entry by
its `command`, removes it, and adds the `SubagentStop` entry instead. No
manual rollback needed.

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
state.
