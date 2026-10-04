# HOME v0 (draft)

Step 1 of PROPOSAL §5: a fresh OS user, given only the declared inventory, comes up working.
First tenant: the new Sonnet agent (proposed name Buster, which is Buster's to accept).

- `inventory`: the declared list. kind is own, loan or absent. Anything not listed that the
  tenant needs is a HOME failure.
- `check`: run AS THE TENANT. It re-execs under `env -i` and verifies each item by effect. Each item
  reports GREEN, RED, ABSENT (declared) or SKIP. It exits 0 only if nothing is RED or SKIP.
- `provision`: run by Will with sudo (`--dry-run` changes nothing). It creates the tenant from the
  inventory, apart from the OAuth login, which is Will's credential, so it prints the command. It
  refuses any existing user it didn't create (root-owned marker `~/.hearth-provisioned`), because on
  an existing agent it would strip ACLs. A dry run against `foil` stops there. `check` and
  `inventory` are installed root-owned under /opt/hearth/home, outside every home, and check's
  `judge` line asserts the tenant can't write them or any directory above them. It follows the choices
  put to Will: a per-tenant Claude Code pinned to 2.1.288, memory declared absent, and no sudo.
- Believed, not checked: `DISABLE_AUTOUPDATER` in `~/.claude/settings.json` env stops Claude
  Code's background updater. `check`'s pinned version line is what proves it, on every run.

Acceptance: on the fresh user, `check` is RED before provisioning and GREEN after. Negative
controls: each inventory item, removed or broken alone, turns only its own line RED.

Run `check` from a login shell as the tenant (`sudo -iu buster /opt/hearth/home/check`), not from inside
a systemd unit with NoNewPrivileges. Under that flag sudo refuses before reading any rules, so the
sudo line can only say "cannot determine". Custody needs a view of other users' real homes, which
a ProtectHome sandbox hides.

Accepted results. Only a run that an operator starts, of the installed absolute path, counts as a
result. Output a tenant produced and pasted is not a pass, however it reads: every line of a copy
is editable, including any guard inside it, so a result with no independent record is a missing
measurement. Inside the script, two things narrow what a copy can do without replacing that rule:
- the inventory path is fixed at /opt/hearth/home/inventory, so a copy still reads the installed
  list, and stripping its own copy of the inventory does nothing;
- the first line prints the path and sha256 of the check and the inventory. A copy can fake that
  line too. It helps an honest reader spot a copy and doesn't stop a dishonest one.

A missing, unreadable or empty inventory is RED, not a pass over nothing. So is an inventory that
leaves out user, home_dir, custody, sudo or judge, or gives one of them a different check.

Observed so far (as foil, 2026-10-04, `check --no-model`):
- claude_bin RED: no `claude` on PATH for a non-will user.
- home_dir RED: an undeclared ACL entry (user:refsdal:--x).
- ledger RED when missing, GREEN at foil 644, RED at 664 and with dir 775.
- custody RED with "no other real home visible": foil's ProtectHome sandbox stubs
  /home/will, so this run can't prove custody. A check that can't see what it guards isn't green.
