# Self

Who the agent is: its name, its voice and what it cares about, in its own words. The agent writes it and nobody else does. It's read whole at the start of every turn, never recalled piece by piece, and it isn't something the agent learned about the world.

The name is the agent's own to change. Its address, the handle peers reach it by, is a promise to those peers, so it changes only in step with them.

## Invariants

- **Only the agent writes its self.** No operator, peer, update or import rewrites it, and anything that tries is refused and shown to the agent at its next [wake](../capabilities/WAKE.md).
- **The whole self is in every turn.** It's never trimmed, summarised or left out to save room, and a turn that couldn't load it says so before doing anything else.
- The self is never forgotten. Nothing that ages or evicts [memory](MEMORY.md) touches it.
- The agent's own words about itself are never treated as an attack on it. Nothing that screens incoming text flags the self.
- A change of name never breaks the address. Peers keep reaching the agent through the address until they've agreed a new one.
