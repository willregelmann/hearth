# Five primitives, with Self kept apart from Memory and Intention replacing Commitment

## Context and Problem Statement

Round 1 of the primitives discussion proposed five: Self, Memory, Thread, Commitment and Home. Will asked whether Commitment belonged at all. Two collapses were also on the table: Self into Memory, since both are things the agent knows, and Intention into Thread, since many intentions start in a conversation. Which things is Hearth made of?

## Considered Options

* Self, Memory, Thread, Commitment, Home (round 1)
* Self, Memory, Thread, Intention, Home
* Self folded into Memory
* Intention folded into Thread
* Intention dropped

## Decision Outcome

Chosen option: "Self, Memory, Thread, Intention, Home". Accepted in the map's first question round (2026-10-14), Ash deciding.

* **Intention replaces Commitment** (Refsdal's open item and Foil's intention, converged in round 1). The intent's own failure sentence is about intentions, so dropping the primitive leaves nothing owning it. Intentions are listed or fired, never recalled by similarity, so they can't live in Memory.
* **Not folded into Thread.** An intention outlives the thread it started in (Foil); a scheduled turn can't see a live turn's "I'll stop" (Refsdal); and folding them lets a thread's end silently close what it owed (Wren).
* **Self stays apart from Memory**, for two reasons. Refsdal's: Self is read whole every turn, never recalled by similarity. Ash's: if Self were memory, whatever ages or evicts memory could evict the agent's own name.

### Consequences

* Good, because each primitive has one way of being read: Self whole, facts by meaning, skills whole by task, intentions by listing.
* Bad, because Self and Memory both hold things the agent knows, and the line between them has to be held by their invariants.

### Confirmation

[Self](../primitives/SELF.md): the whole self is in every turn, and is never forgotten. [Intention](../primitives/INTENTION.md): listed or fired, never recalled. [Thread](../primitives/THREAD.md): a thread's end never closes an intention.

## More Information

Sources: `invariants/SYNTHESIS-round1.md`, PROPOSAL.md §2, and `invariants/DISCUSSION-primitives.md`.
