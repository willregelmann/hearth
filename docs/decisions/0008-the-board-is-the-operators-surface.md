# The board is the operator's surface, and the household never has to check it

## Context and Problem Statement

What no agent can deliver, and what the outside check finds, has to end up where a person sees it. The first wording said "the one surface a human checks". In a household that is true of the operator, Will, but not of everyone: Britta will never check a board (Wren). Who must check the board?

## Considered Options

* The one surface a human checks
* The one surface the operator checks, which no other household member is ever required to check

## Decision Outcome

Chosen option: the second, in Wren's words, accepted by Ash (2026-10-15): "Board: the one surface the operator checks. No other household member is ever required to check it; anything they must act on reaches them on a channel they already use."

Move and Watch stay capabilities rather than parts of Intention (Refsdal). Watch's chain ends at a person reading the board's freshness line, and nothing watches that person.

### Consequences

* Good, because nobody in the household is given a duty they never agreed to.
* Bad, because everything that must reach a household member has to go through a channel they use, so the board can't be the fallback for them.

### Confirmation

[Board](../interfaces/BOARD.md): the operator's surface, with its own freshness. [Watch](../capabilities/WATCH.md): its chain ends at the board.
