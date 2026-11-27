# A wake is persisted before it is acknowledged, and reaches the queue by push or by being polled

## Context and Problem Statement

Two routes lead into a wake: a source pushes it, or Hearth polls the source. [ADR-0015](0015-hearth-names-neither-tapestry-nor-front-desk.md) decided there is no adapter. This record decides what both routes owe, so that one queue serves them. The previous design's host held its wakes in a source's own ledger and recovered them after a restart by asking that ledger what was still pending; with no ledger of the source's to lean on, Hearth must hold its own.

Will's wording (2026-11-17) was "a wake API with support for arbitrary polling", and "I'd love to have first-class support for both" push and poll.

## Decision Drivers

* An accepted wake must survive a restart and must not run twice.
* A source retrying a push must not raise a second wake.
* A poll must not wake the agent for as long as a thing stays visible.
* A failed or hostile check must not look like an empty one.

## Considered Options

* Wakes held in memory, rebuilt from sources at restart
* Wakes persisted by the gateway before acknowledgement, with keys the source chooses
* Wakes handed to the source's own ledger

## Decision Outcome

Chosen option: the second.

* **Wakes are persisted before they are acknowledged**, in a database under Hearth's home. The acknowledgement says whether the wake was new or a duplicate.
* **A wake's identity is its agent, its source label and its key.** A key already accepted from that source for that agent is acknowledged as a duplicate, however long ago. Only long-finished rows are pruned.
* **A poll is edge-triggered.** A key raises a wake when it appears and was absent from the check's previous output, and never while a wake with that key is pending or running. What a check last printed is persisted, in the same transaction as the wakes it raised, so a restart cannot raise again what was raised and a crash cannot keep one without the other.
* **A check fails loudly.** Non-zero exit, timeout or unparseable output raises nothing and is shown on status. The previous keys are kept, so a failing check does not make everything look new when it recovers.
* A key that went away and came back is a new wake, so a source's own identifiers can be reused without being dropped as duplicates.

### Consequences

* Good, because exactly-once is a property of one table and one transaction, not of cooperation between two systems.
* Good, because a source needs only a key it can repeat.
* Bad, because a source that reuses a key for different content, from the same source, gets its second wake swallowed as a duplicate unless the first was polled and went away.
* Bad, because the gateway's database is now the one thing whose loss loses wakes.

### Confirmation

[Wake](../primitives/WAKE.md): persisted before acknowledged, duplicates acknowledged, survives a restart. [Poll](../capabilities/POLL.md): edge-triggered, persisted, failures loud.

## More Information

Written by the builder of the change, with the owner's decisions as the brief. The options are the ones the builder considered, not a recorded discussion.

Delivery is at least once and completion is exactly once: a turn that was killed after showing a wake runs again, and is told so. Hearth cannot know what the first turn did.
