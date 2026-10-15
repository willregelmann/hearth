# Intention

Something the agent means to come back to, open until it's closed with a recorded exit. A promise to a peer is one kind. "Check the deploy at 20:30" is another. Most have nobody waiting: a check that closes on a test, a draft that closes on a condition in the world. Who is waiting, when anyone is, is something an intention can carry, not something every one must.

An item has a condition, and a way of checking it. It can be met only once that check has been shown to fail on the same path; until then it is a draft. A container groups items under one owner and one review date.

Intentions are listed or fired, never recalled when they seem relevant. Every open one is seen by the agent's own sweep, and something outside the agent checks that the sweep ran.

How each invariant is proven, and the checks on those checks, are in [INTENTION-controls.md](../../INTENTION-controls.md).

## Invariants

- **Every intention has a named owner and a review date, and every item has a condition. An item can be met only once its check has been shown to fail on the same path; until then it is a draft.** A change to who or where the check runs, or to anything it declares it depends on, is a new path; nothing else is.
- **Every intention ends in exactly one of three ways: met, dropped or failed.** Met takes an observation and a check that passed; for a delivery, met is "delivered" or "delivered, altered" (below). Dropped takes a reason, and names the successor when one replaces it. At its review date an item becomes due: the owner exits it or moves the date with an observation. Only an awaited answer that hasn't come by then is failed.
- An item's condition is fixed once its check has gone red or been observed. After that a changed condition means the item fails and a successor opens. A container can't close while it holds open items, unless the same step closes or moves them.
- **Only the owner writes its own ledger, through the ledger or directly to its storage.** Anyone else who sees a failure sends it to the owner, who records it. Where two owners share one OS user or one process this can't be enforced, and it's reported as not enforced, never as passing.
- **Every transition names the version it expects; a stale one is refused loudly, as an error the attempting turn must handle, never a silent no-op or a value that reads as success.** Any report of a write carries the version that write produced (the writer's own committed version, never one read back from elsewhere) and what it claims is at that version, in a form the receiver can recompute; whoever relies on it checks both against current state.
- Before any act with side effects, the agent claims the item for a limited time, and an act that can't finish within what's left of its claim doesn't start. If the claim runs out before the act is known to have finished, the outcome is unknown, and an unknown outcome is never retried automatically.
- Every exit reaches whoever is waiting, and every review reaches its owner. Delivered means taken in, unaltered, by a named way of checking that's declared for the channel. An alteration that's declared is a different exit ("delivered, altered"), a delivery nobody can check is unmeasured, never a success, and one that can't be delivered goes to the [board](../interfaces/BOARD.md).
- A request between two agents opens one item in each agent's own ledger. The asker opens its own and asks; the other agent opens its own and acknowledges. Neither is counted as paired until that acknowledgement arrives.
- **The sweep reads every open item from the ledger itself; one it can't read is an error on the board, never skipped.** Something outside the owner checks that each ledger's sweep ran in time, and a miss goes to the board, never into the owner's ledger. An item put off again and again without new evidence (a check result not seen before on that item; new prose isn't) shows on the board as stalled. Time spent dormant doesn't count, and waking an item doesn't reset the count. Every report an owner rejects is shown there too, with both sides' evidence.
- A move between homes is an intention in the executor's ledger: it switches only when its check holds green across a declared settle window, and otherwise rolls back (see [Move](../capabilities/MOVE.md)).
