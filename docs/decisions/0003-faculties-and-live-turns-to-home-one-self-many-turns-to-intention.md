# Faculties and the live-turns view belong to Home, and one-self-many-turns to Intention

## Context and Problem Statement

PROPOSAL.md §3 listed four rules that cut across primitives: faculties are known, one self many turns, one directory, and wakes fire in the agent's own home. The map has no place for free-floating rules, so each needs an owner. The live-turns view (which turns of the agent are running) also needed a home.

## Considered Options

* Faculties under Self
* Faculties under Home
* The live-turns view under Self
* The live-turns view under Home
* "One self, many turns" as its own rule
* "One self, many turns" as Intention's version check

## Decision Outcome

Decided by Ash in the map's first question round (2026-10-14):

* **Faculties go to Home.** A missing tool is about what the agent depends on, which is Home's subject; it says nothing about who the agent is. Tally's reason: "an absence is loud" is Home's "no silent revocation" applied to faculties. Foil's caution, adopted: Home promises the notice, not that a faculty stays available.
* **The live-turns view goes to Home**, over Refsdal's Self. Self holds only what the agent writes about itself; which turns are running is observed.
* **"One self, many turns" is Intention's version check** (Refsdal): every transition names the version it expects, and a receiver checks any version a message names. Refsdal's wording for the record: "Where a version check existed, it held; the misses were a message with no version (case 4) and a refusal nobody heard (case 5). The directory is early visibility; the CAS on the state, plus a receiver checking any version, and recomputable claim, a message names, is the guard."
* One directory goes to Channels, and "wakes fire in the agent's own home" to Clock.

### Consequences

* Good, because every rule has one owner.
* Bad, because the live-turns view can't prove that no other turn is running, and the map has to say so where it's shown.

### Confirmation

[Home](../primitives/HOME.md): the agent knows which faculties are present; it can see its live turns, and an empty list proves nothing. [Intention](../primitives/INTENTION.md): every transition names the version it expects. [Channels](../interfaces/CHANNELS.md): one directory. [Clock](../interfaces/CLOCK.md): when, never where.
