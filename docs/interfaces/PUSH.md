# Push

How a source raises a [wake](../primitives/WAKE.md) the moment something happens, and how the operator and the agents themselves reach the gateway. On the other side is any program on the same machine that can open a Unix socket under Hearth's home: a source's own process, the `hearth` command, or an agent running it.

The protocol is newline-delimited JSON: one request, one response.

## What passes

| Request | What it does |
|---|---|
| Raise | Accepts a wake for an agent and a conversation, with a source label, a key, an optional note, and an optional delay or not-before time |
| List | Returns wakes, filtered by agent or state |
| Cancel | Cancels a pending wake |
| Agents | Adds, removes or reloads an agent without touching the others |
| Status | Returns what [status](STATUS.md) reports |

## Invariants

- **A raise is acknowledged only after the wake is persisted, and the acknowledgement says whether it was a duplicate.**
- **The socket is readable and writable only by the gateway's own user.**
- **Every request gets a response. A request that can't be honoured gets an error that says why, including one that is malformed, names an unknown agent, or is too large.** Nothing is dropped or accepted in part.
- A raise names its conversation, and a note or a label that is too long is refused, never cut short.
- Raising a wake never starts a turn in the caller's own process, and never waits for the turn.
- Every request is answered whether or not an agent's turn is running.
