# Poll

Raising [wakes](../primitives/WAKE.md) for a source that doesn't push. An [agent](../primitives/AGENT.md) declares [checks](../interfaces/CHECKS.md): each is a command the source ships and an interval. Hearth runs it, and a key it prints that was not in the previous output becomes a wake whose source is the check's name.

A source that wants low latency pushes instead. Both routes land in the same queue and obey the same rules.

Poll is edge-triggered. It raises a wake when something appears, not for as long as it stays.

## Invariants

- **A key raises a wake when it appears in a check's output and was absent from the previous output, and never while a wake with that key is still pending or running.**
- **What a check last printed is kept across restarts, so a restart does not raise again what was already raised.**
- A key that went away and came back raises a wake again.
- **A check that exits non-zero, times out, or prints something that isn't understood raises nothing, and the failure shows on [status](../interfaces/STATUS.md).** It is never read as "nothing to do", and it does not make the previous keys count as gone.
- A check never runs twice at once.
- A wake and the record of what its check last printed change together: neither is kept without the other.
