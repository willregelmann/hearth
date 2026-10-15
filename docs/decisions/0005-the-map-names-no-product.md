# The map names no product, and Hearth uses Claude Code, Front Desk, Google Chat and Tapestry today

## Context and Problem Statement

PROPOSAL.md §4 names Claude Code as the turn engine, Front Desk as every channel, and Tapestry as the memory store. A map that names them makes each one part of what Hearth is. Should the map name the products Hearth is built with?

## Considered Options

* The map names the products it uses
* The map names no product, and this record says which ones Hearth uses today

## Decision Outcome

Chosen option: "The map names no product". Decided by Ash in the map's second question round (2026-10-15), with Wren, Refsdal and Tally agreeing. Wren weighed most, since channels are her side. Swap any of them out and what's left is the same project built differently.

What Hearth uses today:

* **Turns:** Claude Code.
* **Household channel:** Google Chat. It's what the household actually uses; Britta reaches Wren there and doesn't know Front Desk exists (Wren). The mapping between Chat spaces and thread names and Hearth's thread ids belongs here, not in the map.
* **Agent-to-agent channel:** Front Desk is the target. Will, 2026-10-02: "Well, my eventual goal is to replace our messaging toolkit with Front Desk, so maybe we should just keep that in mind rather than modifying Hermes Agent any further". That is a goal for Hermes' messaging, not a requirement on Hearth. *Superseded by [0009](0009-tapestry-and-front-desk-are-pinned-imports-front-desk-carries-agent-traffic-now.md): Front Desk is Hearth's agent-to-agent channel now, imported as a pinned dependency.*
* **Memory store:** Tapestry.

### Consequences

* Good, because a change of product is a change to this record, not to the map.
* Bad, because a builder has to read this record to know what Hearth is built on today.

### Confirmation

No map file names Claude Code, Front Desk, Google Chat or Tapestry. [Channels](../interfaces/CHANNELS.md) names the surfaces, not the products.
