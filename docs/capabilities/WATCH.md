# Watch

The outside check that every agent is still attending to its [intentions](../primitives/INTENTION.md). An agent can't be trusted to notice that it has stopped noticing, so something other than the owner checks that each ledger's sweep ran in time, and reports what it finds where a person will see it.

The chain ends at a person reading the [board](../interfaces/BOARD.md)'s freshness line. Nothing watches that person.

## Invariants

- **Watch never runs as the agent it watches, and never writes into that agent's ledger.** A miss goes to the board as "this ledger is unattended".
- **Watch judges a sweep by the sweep's own record of finishing, read against Watch's clock, never the owner's.**
- A miss is reported every time it's found, until a sweep is seen again. A report sent to an owner and still unacknowledged after one sweep period plus the declared margin is a miss too.
- Watch's own freshness is on the board, so a dead Watch reads as stale, never as all clear. The freshness line counts the ledgers that are declared, not the ones Watch happened to find, so a missing ledger shows as a gap.
- Watch reads only what each agent reports on its [status](../interfaces/STATUS.md). It never reads an agent's [memory](../primitives/MEMORY.md) or threads.
