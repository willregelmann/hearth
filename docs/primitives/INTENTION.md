# Intention

Something the agent means to come back to, open until it's closed out loud. A promise to a peer is one kind. "Check the deploy at 20:30" is another. Most have nobody waiting: a check that closes on a test, a draft that closes on a condition in the world. Who is waiting, when anyone is, is something an intention can carry, not something every one must.

An item has a condition, and a way of checking it that has been shown to fail on the same path before it's trusted to pass. Until then the item is a draft, and a draft can't be met. A container groups items under one owner and one review date.

Intentions are listed or fired, never recalled when they seem relevant. Every open one is seen by the agent's own sweep, and something outside the agent checks that the sweep ran.

## Invariants

- **Every intention has a named owner and a review date, and every item has a condition whose check has been shown to fail on the same path.** A change of home, user, host or installed version counts as a new path.
- **Every intention ends in exactly one of three ways: met, dropped or failed.** Met takes an observation and a check that passed. Dropped takes a reason, and names the successor when one replaces it. Silence by the review date is an exit, not a wait.
- An item's condition is fixed once its check has gone red or been observed. After that a changed condition means the item fails and a successor opens.
- **Only the owner writes its own ledger.** Anyone else who sees a failure sends it to the owner, who records it. Where two owners share one OS user this can't be enforced, and it's reported as not enforced, never as passing.
- **Every transition names the version it expects; a stale one is refused loudly, as an error the attempting turn must handle, never a silent no-op or a value that reads as success.** Any report of a write carries the version that write produced (the writer's own committed version, never one read back from elsewhere) and what it claims is at that version, in a form the receiver can recompute; whoever relies on it checks both against current state.
- Before any act with side effects, the agent claims the item for a limited time. If the claim runs out before the act is known to have finished, the outcome is unknown, and an unknown outcome is never retried automatically.
- Every exit reaches whoever is waiting, and every review reaches its owner. Delivered means taken in, unaltered, by a named way of checking that's declared for the channel. An alteration that's declared is a different exit, and a delivery nobody can check is unmeasured, never a success.
- A request between two agents opens one item in each agent's own ledger. The asker opens its own and asks; the other agent opens its own and acknowledges. Neither is counted as paired until that acknowledgement arrives.
- Something outside the owner checks that each ledger's sweep ran in time, and a miss goes to the [board](../interfaces/BOARD.md), never into the owner's ledger. An item put off again and again without new evidence shows on the board as stalled. Time spent dormant doesn't count, and waking an item doesn't reset the count. Every refusal is shown there too.
- A move between homes is an intention in the executor's ledger: it switches only when its check holds green across a declared settle window, and otherwise rolls back (see [Move](../capabilities/MOVE.md)).
