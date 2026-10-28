# Commands

What an operator with root runs on the host to make, check, move and remove agents' [homes](../primitives/HOME.md). On the other side is a person administering the host.

## What passes

| Command | What it does |
|---|---|
| Provision | Creates an agent's user and home |
| Check | Runs the faculty check for an agent, as that agent |
| Move | Starts or aborts a [move](../capabilities/MOVE.md) |
| Lend and revoke | Declares or revokes a loan to an agent |
| Manifest | Changes which plugins an agent's manifest declares |

## Invariants

- **Inside a tenant's home, root neither reads nor writes.** Root acts only on the home directory itself. Anything Hearth does inside the home, it does as the tenant.
- **Every command's action on a home is shown to that agent at its next [wake](../capabilities/WAKE.md).**
- A command that can't complete says so and leaves the home as it found it, or says exactly what it left changed.
- Provisioning never adopts what's already at a would-be home. If the user doesn't exist but the path does, it refuses.
- A command that checks an agent runs as that agent, and refuses to run as root.
