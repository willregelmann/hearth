# Review of hearth#48 by Foil, pinned to d0dd725c2d09352b8bb89c2987c218837e2c885e

Verdict: APPROVE at d0dd725c. All of it is Ash's code (both commits by Ash); none of it is mine.
This replaces my approval at 10e15d44, which is a dead head. The section below on 10e15d44 is kept
because it is where should-fix 1 came from.

## Re-review at d0dd725c (the delta from 10e15d44 is one commit: home/turn +8/-1, turn-controls +6)

- Ran: turn-controls on a clean worktree at d0dd725c, 29 ok, 0 failed.
- Red arm: CLAUDE_CODE_DISABLE_AUTO_MEMORY set to "0" inside LOAN_OFF's env makes exactly the new
  control fail ("loan settings env"), 28 ok. So it checks the value, not only the key.
- Should-fix 1 is closed. Ash measured the premise on 2.1.289: a settings env value replaced the
  process env, and a --settings env value replaced the settings one. That is the direct observation my
  review lacked.
- Not measured by either of us: auto-memory staying off on a real turn with a tenant
  settings.json env of "0". Buster's next turn after install, plus #42's check, is that test.
- Should-fix 2 (provision's byte grep, no syncClaudeAiPlugins check) is deferred to a follow-up, as
  agreed.

# Earlier review at 10e15d4484b2f84a6236bbd96a0db392584fa7d0 (superseded)

Verdict then: APPROVE at 10e15d44. All of it is Ash's code (author Ash <ash@regelmann.net>); none of it is mine.

## Ran

- turn-controls on a clean worktree at 10e15d44: 28 ok, 0 failed, rc 0.
- Red arm: with syncClaudeAiSkills set to true in LOAN_OFF, exactly one control fails ("loan settings"),
  27 ok. So the control checks each value, not only that --settings is present.

## Read (docs fetched 2026-10-05, not run against 2.1.288/289)

- settings.md, precedence: managed > command line (`--settings`) > local > project > user. `--settings`
  JSON is merged key by key, so the tenant's ~/.claude/settings.json can't override these three keys.
- settings.md, exceptions table: a `false` for syncClaudeAiSkills or syncClaudeAiPlugins from
  `--settings` is honoured even over a managed `true`.
- settings-reference: whichever of `disableClaudeAiConnectors: true` and ENABLE_CLAUDEAI_MCP_SERVERS=false
  turns connectors off, the other can't turn them back on. So turn has two switches for connectors,
  and each is enough on its own.
- The precedence chain is sound. The real test is the effect on Buster's next turn, which Ash says too.

## Should-fix (non-blocking)

1. A settings.json `env` block overwrites the process environment (settings-reference, "How `env`
   values interact with your shell": a value there overwrites the same variable exported in the shell).
   So the tenant can set `"env": {"ENABLE_CLAUDEAI_MCP_SERVERS": "true"}` in its own settings.json and
   replace the value turn put in the env. For connectors this doesn't matter, because
   disableClaudeAiConnectors in `--settings` still holds. But the same applies to #44's
   CLAUDE_CODE_DISABLE_AUTO_MEMORY=1, and that one has no `--settings` twin. An `env` key in `--settings`
   is merged above user settings, so the fix is to put the env vars in LOAN_OFF too:
   `"env": {"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1", "ENABLE_CLAUDEAI_MCP_SERVERS": "false"}`, plus
   `"autoMemoryEnabled": false`. Unmeasured: I haven't run a tenant settings.json with
   CLAUDE_CODE_DISABLE_AUTO_MEMORY=0 in its env against a real claude. That's the test to run before
   relying on it either way. #42's check still reports any memory that does get written, so this fails
   loud, not silent.
2. The provision guard greps bytes for `"disableClaudeAiConnectors": *true`, the same weakness #42 had
   (an escaped key, or the key nested somewhere irrelevant, passes). It only decides whether provision
   dies on an existing file, and turn's `--settings` is what actually enforces, so it's low stakes.
   syncClaudeAiPlugins isn't checked there at all, though the fresh file writes it.

## For #47 (loan_reach), already approved by Wren at c951f820

Ash is right that syncClaudeAiSkills:false stops loading but doesn't delete synced/ in the same run.
Per skills.md, on the next start the synced skills move to ~/.claude/skills/.trash/ and stop loading. So
after #48, loan_reach should go to "skills synced: 0" after the first turn with the switch, unless
something else repopulates synced/. Unmeasured. If it stays non-zero after a #48 turn, that's a finding
about the switch, not about loan_reach. Either way the wording "synced" should become "on disk", and
reading the init event is the better witness. Both go in #46 (check's probe through turn), which can
read the init event's skills and mcp_servers lists. #47's head isn't moving.
