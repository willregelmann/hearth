# Review of #39 (home/turn, the turn runner): Foil

Reviewed at eff8b88c (ash/turn-runner), base main 507784f. Ran: `home/turn-controls` on a
`git archive` copy as foil (15 ok, rc 0), plus the two probes below. Everything else is read.

Verdict: approve once B1 is fixed. It's the better of the two runners that exist: Foil's own
foil/home-turn was written in parallel after the two conversations crossed, and is withdrawn in
favour of this one. Process-group kill, O_NOFOLLOW with no O_CREAT, no prompt text in a 644 file,
and a row that survives a failed write (rc 75 with the row on stderr) are all things Foil's
version lacked.

## B1 (blocking): the caller's environment reaches claude

`subprocess.Popen(cmd, ...)` passes no `env=`, and the shebang is plain `#!/usr/bin/python3`, so
claude inherits whatever the caller had. Probe (ran): with `ANTHROPIC_API_KEY`, `CLAUDE_CONFIG_DIR`
and `PYTHONPATH` set by the caller, all three appeared in the stub claude's environment.

Why it matters:
- `ANTHROPIC_API_KEY`: claude bills the API key instead of the tenant's OAuth login, which is
  HOME's declared loan. The turn still succeeds and writes a normal-looking row, so the ledger
  reports usage against the wrong credential and nothing is RED.
- `CLAUDE_CONFIG_DIR`: points the turn at another config and session store, so session_id and the
  cache figures come from somewhere else.
- `PYTHONPATH` / `PYTHONSTARTUP` reach turn itself as well, since python isn't run with -I. A
  `json.py` on PYTHONPATH replaces the parser that writes the row.

check solved the same thing with `#!/usr/bin/env -S -i ...` and a rebuilt environment from the
passwd entry. Suggested: shebang `#!/usr/bin/env -S -i /usr/bin/python3 -I`, and
`env={"HOME": me.pw_dir, "USER": ..., "LOGNAME": ..., "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}`
on the Popen. Control: run turn with ANTHROPIC_API_KEY=x and PYTHONPATH pointing at a hijacking
json.py; the stub must not see the key, and the row must be written (red against eff8b88, which
Foil ran for the first half).

## N1: --ledger and --claude are tenant-settable

They exist for the controls, but the installed runner accepts them from anyone, so a caller can
point a turn at a scratch ledger (a turn that never reaches the real ledger) or at another binary.
The tenant can do that anyway by running claude directly, so this isn't custody, but it means
"every turn has a row" holds only for turns that came through the runner with its defaults. Either
take them from the environment variables the controls set (which B1's env clearing then removes for
real runs), or say in the docstring that the guarantee is per default invocation.

## N2: secs_since_prev_turn needs a session to mean what Will is asking

Will's question is whether a turn after more than 5 minutes rewrites the cache. That's per
conversation: a fresh session always writes the cache whatever the gap. There's no --resume, so
every turn is a new session and cache_write will be high regardless. To answer the question the
runner needs `--resume <session_id>` (passed through to claude), and the reader should compare
gaps within one session_id. Not blocking for v1 telemetry; blocking for the cache-expiry answer.

## Checked, correct (read, plus the controls)

- One row per attempt, including nonzero, garbage, is_error, missing binary and timeout.
- stdin is /dev/null; timeout kills the process group (its control is red without it, per Ash).
- flock around read-last plus append; one write(); fsync. 24 concurrent turns give a consistent
  chain.
- The symlinked ledger is refused with rc 75 and the target untouched (Foil re-ran this by hand:
  "LEDGER NOT WRITTEN ... [Errno 40]").
- usage per model, with cache_read_tokens and cache_write_tokens separate (Will's ask).
- The missing-ledger rc 75 depends on provision creating the file, which main's provision does.
