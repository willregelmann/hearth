# HOME v0 (draft)

Step 1 of PROPOSAL §5: a fresh OS user, given only the declared inventory, comes up working.
First tenant: the new Sonnet agent (proposed name Buster, which is Buster's to accept).

- `inventory`: the declared list. kind is own, loan or absent. Anything not listed that the
  tenant needs is a HOME failure.
- `check`: run AS THE TENANT. It re-execs under `env -i` and verifies each item by effect. Each item
  reports GREEN, RED, ABSENT (declared) or SKIP. It exits 0 only if nothing is RED or SKIP.
- `provision`: run by Will with sudo (`--dry-run` changes nothing). It creates the tenant from the
  inventory, apart from the OAuth login, which is Will's credential, so it prints the command. It
  refuses any existing user it didn't create (marker `~/.hearth/provisioned-by-hearth`), because on an
  existing agent it would strip ACLs. A dry run against `foil` stops there. It follows the choices
  put to Will: a per-tenant Claude Code pinned to 2.1.288, memory declared absent, and no sudo.
- Believed, not checked: `DISABLE_AUTOUPDATER` in `~/.claude/settings.json` env stops Claude
  Code's background updater. `check`'s pinned version line is what proves it, on every run.

Acceptance: on the fresh user, `check` is RED before provisioning and GREEN after. Negative
controls: each inventory item, removed or broken alone, turns only its own line RED.

Run `check` from a login shell as the tenant (`sudo -iu buster ./hearth/home/check`), not from inside
a systemd unit with NoNewPrivileges. Under that flag sudo refuses before reading any rules, so the
sudo line can only say "cannot determine". Custody needs a view of other users' real homes, which
a ProtectHome sandbox hides.

Observed so far (as foil, 2026-10-04, `check --no-model`):
- claude_bin RED: no `claude` on PATH for a non-will user.
- home_dir RED: an undeclared ACL entry (user:refsdal:--x).
- ledger RED when missing, GREEN at foil 644, RED at 664 and with dir 775.
- custody RED with "no other real home visible": foil's ProtectHome sandbox stubs
  /home/will, so this run can't prove custody. A check that can't see what it guards isn't green.
