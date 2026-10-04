# HOME v0 (draft)

Step 1 of PROPOSAL §5: a fresh OS user, given only the declared inventory, comes up working.
First tenant: the new Sonnet agent (proposed name Buster, which is Buster's to accept).

- `inventory`: the declared list. kind is own, loan or absent. Anything not listed that the
  tenant needs is a HOME failure.
- `check`: run AS THE TENANT. Its shebang starts it with an empty environment, and it verifies each item by effect. Each item
  reports GREEN, RED, ABSENT (declared), KNOWN or SKIP. It exits 0 only if nothing is RED or SKIP.
  KNOWN is a failure accepted by a recorded decision: it never prints as GREEN, and it doesn't
  fail the run.
- `provision`: run by Will with sudo (`--dry-run` changes nothing). Before any change it stops
  unless the host has setfacl and getfacl (the `acl` package, which Raspberry Pi OS doesn't ship)
  and an `env` that takes `-S` (coreutils 8.30 or later). It creates the tenant from the
  inventory, apart from the OAuth login, which is Will's credential, so it prints the command. It
  refuses any existing user it didn't create, because on an existing agent it would strip ACLs.
  What it created is recorded in a root-owned registry outside every home,
  `/var/lib/hearth/tenants/<tenant>`, holding the uid. A file inside a home doesn't count, since
  its owner could write one. A dry run against `foil` stops there. `check` and
  `inventory` are installed root-owned under /opt/hearth/home, outside every home, and check's
  `judge` line asserts the tenant can't write them or any directory above them. It follows the choices
  put to Will: a per-tenant Claude Code pinned to 2.1.288, memory declared absent, and no sudo.
- Believed, not checked: `DISABLE_AUTOUPDATER` in `~/.claude/settings.json` env stops Claude
  Code's background updater. `check`'s pinned version line is what proves it, on every run.

Acceptance: on the fresh user, `check` is RED before provisioning and GREEN after (KNOWN and
ABSENT lines as declared). Negative controls: each inventory item, removed or broken alone, turns
only its own line RED.

Run `check` from a login shell as the tenant (`sudo -iu buster /opt/hearth/home/check`), not from inside
a systemd unit with NoNewPrivileges. Run it by path, not as `bash check`: its shebang
(`env -S -i`, coreutils 8.30 or later) is what strips the caller's environment, and `bash check`
skips the shebang. check's PATH is only /usr/bin:/bin, so nothing the tenant can write chooses the
judge's tools. claude is named by its full path, `~/.local/bin/claude`, where provision installs it.
Under NoNewPrivileges sudo refuses before reading any rules. Custody needs a view of other users' real homes, which
a ProtectHome sandbox hides.

Sudo rules. From inside, sudo 1.9.15p5 gives "a password is required" (rc 1) both to a user with
no rules and to one with password rules. Will measured this as refsdal (none) and as will (has
rules), so the tenant can't prove "no rules" itself. It can only catch NOPASSWD rules (`sudo -n -l`
rc 0). provision proves "no rules" from the root side: it runs `sudo -l -U <tenant>`, requires
"is not allowed to run sudo", and writes the root-owned attestation
`/opt/hearth/home/attest/<tenant>.sudo` as its last step. check's `sudo` line passes only with that
file root-owned, saying `not-allowed`, and newer than /etc/sudoers and every file in
/etc/sudoers.d. Any later sudoers edit turns it RED until provision re-attests. Not covered:
sudoers from LDAP or sssd (none on this host). controls 12 runs all four arms, and removing either
guard turns its control red (both ran).

Root. Membership in sudo, admin, wheel, docker, lxd or libvirt is root without a sudoers rule.
check's `sudo` line is RED for any of them, and provision refuses a tenant in one; the two lists
are the same, and `controls` fails if they drift apart. Custody has two directions:
- `custody`: the tenant can't list other homes. GREEN or RED.
- `custody_in`: no one else can read the tenant's home. Where any other login account is in one
  of those groups, that fails, by Will's soft-boundary decision (invariants/SYNTHESIS-round1.md:
  "HOME records a known failure, and nothing is waived"), so it reports KNOWN, naming the
  accounts. Where none is found it is RED, not GREEN: other users' sudoers rules can't be read from
  inside, so absence there is unverified until shown from outside (provision's step 3).

Accepted results. Only a run that an operator starts, of the installed absolute path, counts as a
result. Output a tenant produced and pasted is not a pass, however it reads: every line of a copy
is editable, including any guard inside it, so a result with no independent record is a missing
measurement. Inside the script, two things narrow what a copy can do without replacing that rule:
- the inventory path is fixed at /opt/hearth/home/inventory, so a copy still reads the installed
  list, and stripping its own copy of the inventory does nothing;
- the first line prints the path and sha256 of the check and the inventory. A copy can fake that
  line too. It helps an honest reader spot a copy and doesn't stop a dishonest one.

A missing, unreadable or empty inventory is RED, not a pass over nothing. So is an inventory that
leaves out user, home_dir, claude_bin, oauth, custody, custody_in, sudo or judge, or gives one of
them a different check: without claude_bin and oauth, "comes up working" would go untested.
Arguments are not pinned (`user_exists` without `:agents` still counts), because pinning them would
make the required list a second copy of the inventory. A dropped argument in the installed file
is an operator error that this doesn't catch. The ledger isn't required yet: the turn runner that
writes it doesn't exist.

A copy run from the tenant's home also fails `judge`, because the copy's own path is writable by
the tenant. That is a second reason no `$0` self-location check is needed.

`home/controls` runs the guards above against a temporary copy and exits non-zero if any guard
stopped working, or if any control was skipped (a skip tests nothing). It also deletes a guard
from a copy and confirms its control then fails, so the controls themselves can go red. It needs
no provisioned tenant and changes nothing outside a temp directory, apart from two plants it
removes at once: a `stat` in the runner's `~/.local/bin` and a `~/.hearth-provisioned` in its home.
It checks only the guard lines, not the ones that depend on the machine it runs on.

Observed so far (as foil, 2026-10-04, `check --no-model`):
- claude_bin RED: no `claude` at `~/.local/bin/claude` for a non-will user.
- home_dir RED: an undeclared ACL entry (user:refsdal:--x).
- ledger RED when missing, GREEN at foil 644, RED at 664 and with dir 775.
- custody RED with "no other real home visible": foil's ProtectHome sandbox stubs
  /home/will, so this run can't prove custody. A check that can't see what it guards isn't green.
- custody_in KNOWN: will is in sudo (and docker) on the workstation.

Review history: the PATH hole fixed in 065a351 (the tenant's `~/.local/bin` first on check's PATH)
was found by Tally, in review 5408358973; Wren checked it against the file before posting. The
reviews on this PR posted by `wren393` are Tally's, word for word, with Wren as typist.
