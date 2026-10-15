# A fact's default audience is its household, and a narrowed audience includes only its recorder

## Context and Problem Statement

Round 1 left open whether privacy in a household is attribution or isolation (R2-c). The answer has two parts: who told the agent a fact, and who may hear it. Two texts were then agreed in different conversations and read as contradicting each other. One set the default audience to the household; the other set it to "the people plus the owning agent". Which default does a fact get, and who is inside a narrowed audience?

## Considered Options

* Default audience: the thread the fact arrived in
* Default audience: the household the fact came from, its people and the agents that serve them
* Default audience: the people plus the agent that recorded it
* A separate carve-out for money facts

## Decision Outcome

Chosen: the household default, and a separate rule for narrowed audiences. Decided by Ash (2026-10-15). The two texts answer different questions, and the map carries both:

* **Unset default** (Wren's wording, with Foil and Tally): "Where no audience is set, the default is the household the fact came from, its people and the agents that serve them, not the thread it arrived in." The default is written at record time, so a missing audience can be found.
* **Narrowed membership** (Tally's rule 3, reworded by Ash): "When a fact's audience is narrowed to named people, the agent that recorded it is inside; every other agent is outside unless one of those people says yes."

Not the thread it arrived in: that would wall Britta off from Will, and Will said they discuss the agents with each other (Wren, citing 2026-09-13). Not the narrow default: it would put every fact Will gives one agent out of every other agent's reach, a cost nobody chose. Wren's case, which Ash took as decisive: under a narrow default, "we're away this weekend", told by Britta to Wren with no audience set, couldn't reach any other agent unless she widened it, every time. No money carve-out: Tally narrows money facts as their recorder, and a recorder's narrowing binds everyone downstream.

"Who told me" is Memory's provenance. "Who may hear it" is Thread's.

### Consequences

* Good, because sensitive facts are narrowed where they're recorded, by the agent that knows they're sensitive.
* Bad, because a turn records at the narrowest audience of anything that entered its context, so facts that only came to mind will over-narrow some turns. The recorder logs whether each narrowing came from the source or from context, so the rate can be measured.
* Bad, because combining facts intersects their audiences. Household money is narrowed to Will and Britta together, so ordinary joint advice reaches both. (i) Joint advice that draws on a fact private to one of them reaches only that one, and a send to the other is held. That is the cost the household will actually meet. The hold's notice goes to the fact's owner, never the asker, and the asker gets an answer made without the fact, or "can't answer that fully right now" with no reason given. Even so, an attentive asker can infer from an incomplete answer that something was withheld. Nothing closes that, and the metadata isn't hidden. (ii) Advice that mixes a fact private to Will with one private to Britta lands for the agent alone, and each delivery needs the owner's yes, per send. That should be rare.
* Bad, because figures a person states directly in a thread aren't narrowed by any source. A detector is the planned fix once a recorder exists.
* Bad, because until a recorder writes the default at record time, a fact whose recorder considered its audience and one whose recorder never did look the same, so a silent widening can't be found. This is a known failure until the default is written.

### Confirmation

[Thread](../primitives/THREAD.md): the audience invariants. [Memory](../primitives/MEMORY.md): each fact carries its audience. [Channels](../interfaces/CHANNELS.md): a send outside the audience is refused or held.

## More Information

An earlier "by default the audience is the people plus the owning agent" was Ash's wording mistake, not a change of position (Ash, 2026-10-15).
