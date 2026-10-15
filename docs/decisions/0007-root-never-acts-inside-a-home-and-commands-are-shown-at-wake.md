# Root never acts inside a home, and every command is shown at the agent's next wake

## Context and Problem Statement

Root on a host can do anything to an agent's home, and a readable record of what it did doesn't help if the agent never reads it (Tally). Root can also edit that record. What does the map promise about root's actions on a home?

## Considered Options

* Every root action on a home is shown at the agent's next wake
* Actions taken through commands are shown at the next wake; root acting outside commands is a known failure
* Root may act inside a home when a command needs it

## Decision Outcome

Chosen: the second, with no exception for commands. Decided by Ash (2026-10-14), from Tally's proposal and Foil's split; Tally agreed.

* Actions taken through commands are an invariant, because the harness controls both the action and the wake, so it can be tested: a red arm suppresses the display and must be caught.
* Root acting outside commands can't be promised, so it is a known failure on any host where root exists.
* Inside a tenant's home, root neither reads nor writes (Refsdal, from the review of hearth #33). `home/provision` already keeps this at 734a7552. An "except through commands" exception would reopen the planted-link path, so it's reconsidered only for a concrete command that needs root inside a home.
* Home's mechanics (permissions, pinned versions, provisioning steps, install paths) move to the build docs.

### Consequences

* Good, because every action Hearth itself takes on a home reaches the agent.
* Bad, because root outside commands is invisible to the map, and "no agent can write the faculty check's record" isn't met today: check's results aren't recorded independently of the run.

### Confirmation

[Commands](../interfaces/COMMANDS.md): root neither reads nor writes inside a home; every action is shown at the next wake. [Home](../primitives/HOME.md): no agent can write the faculty check or its record. [Wake](../capabilities/WAKE.md): what changed in the home is shown as one block.
