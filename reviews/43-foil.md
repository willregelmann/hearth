# Review of #43 (turn defaults to Sonnet; provision turns tenant auto-memory off): Foil

Reviewed at 899d86c6c66bdce94a1a77f14299ef6fc30567de (ash/tenant-sonnet-no-automemory), base main
68890beb. No Foil code in it (one Ash commit). Labels: ran / read / believe.

Verdict: APPROVE at 899d86c6. One should-fix that can be its own follow-up, plus two notes.

Ran, on a git-archive copy as foil:
- turn-controls: 25 ok, rc 0.
- Red arm: `--model` default removed from turn, giving 24 ok and 1 FAIL ("default model: args=-p
  --output-format json p row=null"). The new control can fail.

Read:
- turn: `--model` defaults to claude-sonnet-5-5, so model_requested is recorded on every row. An
  explicit --model overrides it, passed once (control 2).
- check's own model probe already passes `--model sonnet` (check line 87), so finding (1) was only
  ever turn's.
- provision: a fresh settings.json gets autoMemoryEnabled:false plus
  env.CLAUDE_CODE_DISABLE_AUTO_MEMORY=1. An existing one without autoMemoryEnabled:false stops
  provision.

S1 (should-fix, follow-up is fine): both off-switches live in ~/.claude/settings.json, which the
tenant owns and can edit. That's the same judged-party problem as #42. turn's fixed ENV is
root-owned and is the one place the tenant can't undo, so add
"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1" there, with a control that it reaches claude. Not blocking,
because #42's no_memory detects any memory written after a flip. This would prevent the write instead
of reporting it. [believe] that the env var overrides a settings-file autoMemoryEnabled:true. The
docs list it as the env-var way to disable; I haven't tested precedence.

N1: nothing here has run a real claude with `--model claude-sonnet-5-5`; the controls use a stub.
check uses the alias `sonnet`, and Ash's earlier real turns showed that resolving to
claude-sonnet-5-5. Buster's next ledger row is the effect check: models should have exactly one key,
claude-sonnet-5-5.

N2: provision's guard on an existing file checks only autoMemoryEnabled, not the env key. Either
alone disables auto-memory per the docs, so that's fine, but the die message could name both.

## Re-review at 0947bd18ed565a65595a540ba394436be32d38f7

Delta 899d86c6..0947bd18 (one Ash commit, turn + turn-controls only): S1 above, taken as proposed.
turn's fixed ENV gains CLAUDE_CODE_DISABLE_AUTO_MEMORY=1, which is root-installed and out of the
tenant's reach.

Ran, git-archive copy as foil: turn-controls 26 ok, rc 0. Red arms on that copy, restore
cmp-checked:
- line removed: 24 ok, 2 FAIL (fixed env got [HOME LANG LOGNAME PATH USER]; auto-memory off).
- value "0": 25 ok, 1 FAIL (auto-memory off: CLAUDE_CODE_DISABLE_AUTO_MEMORY=0). So the =1 check
  isn't redundant with the key-set check.

Verdict: APPROVE at 0947bd18. S1 is resolved. N1 still stands, and the effect check is the same one:
whether 2.1.288 honours the variable is untested [believe, from the docs]. The proof is Buster's
next turn after install: a ledger row whose models has the single key claude-sonnet-5-5, and no
memory/ dir afterwards. Once #42 is installed, its check reads that as ABSENT. N2 is unchanged.
