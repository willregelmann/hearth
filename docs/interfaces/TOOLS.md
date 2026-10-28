# Tools

What the agent's model calls during a turn to act on its own state: its [memory](../primitives/MEMORY.md), its [intentions](../primitives/INTENTION.md), its [threads](../primitives/THREAD.md) and its [self](../primitives/SELF.md). On the other side is the agent itself, as its model.

## What passes

| Tool | What it does |
|---|---|
| Recall | Returns memories by meaning, each with who it came from, whether it's checked, and its audience |
| Remember | Records a fact or a skill, with its provenance and audience |
| Load skill | Returns a whole skill |
| Intentions | Opens, amends, closes and lists the agent's own intentions |
| Send | Passes a message on a thread, within audience |
| Set wake | Brings the agent back to this thread at a time it chooses ([Clock](CLOCK.md)) |
| Write self | Changes the agent's own self |

## Invariants

- **A tool acts only on the calling agent's own home.** No tool writes another agent's ledger, memory or self. Reaching another agent goes through [channels](CHANNELS.md).
- Every tool that changes state takes the version it expects, and a stale one is an error the turn sees.
- A tool that fails says it failed. It never returns an empty result in place of an error.
- The tools an agent has are the ones its manifest declares and its home's faculty check found present, and an absent one is reported, not silently missing.
- **Every turn is told how to wait.** A wake it sets brings it back to this thread, an answer from a peer arrives later as a new message, and nothing it calls holds the turn open until someone replies.
- A tool behaving differently on a different host is a bug.
