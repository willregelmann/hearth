# Home

Everything the agent depends on and everything it holds: its own OS user, its files, its credentials, its workspace, and its faculties (its memory, its tools and its interpreter). Each of these is either the agent's own or a declared loan. Whichever it is, the agent holds it in exclusive custody unless it's declared shared.

A loan is declared to the agent whose home it is, recorded with who declared it, when, and its scope. It can be revoked, but never silently.

Home also holds the agent's view of itself running: which of its faculties are present right now, and which of its turns are live.

## Invariants

- **Everything the agent depends on is its own or a declared loan, and everything it holds is in its exclusive custody unless declared shared.** A declaration counts only when it's made to the agent whose home it is, with who made it and when.
- **At most one agent runs as any OS user.** An agent runs as its own user. The one exception is a human's first agent, which may run as that human's own user; every further agent gets its own.
- **The agent always knows which of its faculties are present.** An absent faculty is reported to the agent before its turn writes anything. Home promises the notice, not that the faculty stays available.
- A loan is never revoked silently. Revoking one is shown to the agent at its next [wake](../capabilities/WAKE.md).
- No agent can write the faculty check, its record of what it found, or any loan record, its own or another agent's.
- Every action taken on a home through [commands](../interfaces/COMMANDS.md) is shown to the agent at its next wake.
- The agent can see which of its turns are live. An empty list proves nothing: the guard against two turns colliding is the version check in [Intention](INTENTION.md), not this list.
- A home moves only through [Move](../capabilities/MOVE.md).
