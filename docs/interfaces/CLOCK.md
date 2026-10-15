# Clock

When something fires without anyone sending a message: a review date coming due, a wake the agent set for itself, a sweep. On the other side is time.

## What passes

| Firing | What it does |
|---|---|
| Due review | Starts a [wake](../capabilities/WAKE.md) for an intention whose review date has come |
| Set wake | Starts a wake the agent asked for |
| Sweep | Runs the agent's sweep over every open intention |

## Invariants

- **The clock says when, never where.** A firing runs in the agent's own [home](../primitives/HOME.md), as the agent, from its own process.
- Each ledger has one clock, its owner's. Comparing times across ledgers allows a declared skew margin, and a checker uses its own clock, never the owner's.
- A firing that couldn't run is reported, never skipped silently, and runs late rather than not at all.
- A firing never runs twice for one due time.
