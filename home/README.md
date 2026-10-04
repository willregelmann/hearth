# HOME v0 (draft)

Step 1 of PROPOSAL §5: a fresh OS user, given only the declared inventory, comes up working.
First tenant: the new Sonnet agent (proposed name Buster, which is Buster's to accept).

- `inventory`: the declared list. kind is own, loan or absent. Anything not listed that the
  tenant needs is a HOME failure.
- `check`: run AS THE TENANT. It re-execs under `env -i` and verifies each item by effect. Each item
  reports GREEN, RED, ABSENT (declared) or SKIP. It exits 0 only if nothing is RED or SKIP.
- `provision`: not written yet. It waits on Will's answers (install location, memory in v0, sudo).

Acceptance: on the fresh user, `check` is RED before provisioning and GREEN after. Negative
controls: each inventory item, removed or broken alone, turns only its own line RED.

Observed so far (as foil, 2026-10-04, `check --no-model`):
- claude_bin RED: no `claude` on PATH for a non-will user.
- home_dir RED: an undeclared ACL entry (user:refsdal:--x).
- ledger RED when missing, GREEN at foil 644, RED at 664 and with dir 775.
- custody RED with "no other real home visible": foil's ProtectHome sandbox stubs
  /home/will, so this run can't prove custody. A check that can't see what it guards isn't green.
