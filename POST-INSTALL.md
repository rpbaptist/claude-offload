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
confirm **no** review message appears.

*If a review message appears:* the `subagent_type` filter in
`hooks/local-exec-review.py` isn't matching. Add a debug line dumping the
payload to a file and inspect what the field is actually called.

## 3. The hook fires for local-exec

In a git repo with a **clean tree**, explicitly ask: *"use local-exec to write a
`greet(name)` utility in `src/greet.py`"*.

Expect, after the subagent returns, a message stating its output is unreviewed
and instructing a `git diff` — and then Claude actually running `git diff` and
commenting on the code before saying it's done.

*If nothing appears:* confirm the `PostToolUse` entry is in
`~/.claude/settings.json` and that the command path is executable. Test it
standalone:

```sh
echo '{"cwd":"'"$PWD"'","tool_input":{"subagent_type":"local-exec"}}' \
  | ~/.claude/hooks/local-exec-review.py; echo "exit=$?"
```

Expect the message on stderr and `exit=2`.

*If the message appears but Claude ignores it:* that's the interesting failure.
Note it — the enforcement mechanism is the whole basis for delegating to a model
this small.

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
followed by the Task call.

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

Compare a delegated boilerplate task against doing the same thing directly.
Watch for the failure mode where a bad generation costs two retries plus a
review and ends up more expensive than writing it once. If that's common,
narrow what gets delegated — the fix is scope, not prompt engineering.

Also confirm `--context` files aren't blowing the model's window on larger
files; whole-file generation degrades past a few hundred lines.

---

## Upgrading from a pre-#1 install

If `~/.claude/settings.json` still has `"matcher": "Task"` under
`PostToolUse` (from an install before the
[Task→Agent rename fix](https://github.com/rpbaptist/ollama-subagent/issues/1)),
the hook never fires — the harness's subagent-launching tool is actually named
`Agent`, not `Task`. Rerun `./install.sh`: it detects the existing entry by
its `command`, not its stale matcher, and rewrites the matcher to `"*"` in
place. No manual rollback needed.

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
