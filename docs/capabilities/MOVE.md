# Move

Moving an agent's [home](../primitives/HOME.md): to another user, another path, another host or another installed version. A move is an [intention](../primitives/INTENTION.md) in the executor's ledger, opened before anything moves, and it follows Intention's rules on custody and versions without restating them.

Whether to move, and when, is the agent's consent and the operator's call. How the switch and the rollback behave is fixed.

## Invariants

- **A home moves only by a procedure the agent has reviewed.** Before the move starts, the agent has seen the check, the deadline, the rollback and who carries it out, and it can trigger the rollback itself at any time until the move is green.
- **The switch counts as green only if its check holds green across a declared settle window.** If it holds red across the window, or isn't green by the deadline, the executor rolls back without waiting for anyone and records why.
- The rollback has its own check: the agent is served from its old home with its state as it was. If that check fails or the rollback stops partway, the executor stops with a by-hand instruction and reports it to the [board](../interfaces/BOARD.md) at once, not when the agent next wakes.
- Once green, the executor disarms. A later failure is a new intention in the new home, never a rollback, because rolling back would discard what the agent wrote there.
- Both checks have been shown green on the real path and red on a broken one before the switch is armed, on the target path and as the target user.
- **The move doesn't start until the executor has acknowledged it; an unacknowledged switch protects nothing.**
- Firing and disarming race on the same version, and exactly one wins.
- Moving one agent never stops another.
