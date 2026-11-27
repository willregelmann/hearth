# A session starts with the agent's pending wakes, and an agent can cancel its own wake with a reason

## Context and Problem Statement

[ADR-0014](0014-hearth-is-a-gateway-and-a-claude-code-plugin.md) took the intention ledger out of Hearth. What the ledger was for was two things: what the agent has said it will come back to should stay in front of it, and something it no longer means to do should be closed with a reason rather than left to go stale. With the ledger gone, an agent sets a wake for itself with a note when it means to come back ("check the deploy at 20:30"). So its pending wakes already are its open intentions. But nothing shows them to it, and only an operator can cancel one, with no reason given. Should Hearth show an agent its pending wakes, and let it cancel its own?

## Decision Drivers

* On the agents' earlier harness, mechanisms an agent had to choose to use went unused. A wake-me-later tool was built, tested and installed on two machines and used by neither agent. Initiatives also sat untouched for hundreds of hours while reactive work filled the time. What an agent is shown without asking gets used; what it has to remember to ask for doesn't.
* A wake set in one conversation is invisible from the agent's other conversations, so one conversation can't see what another has promised.
* Hearth stays minimal: no new primitive, and no store beside the wake queue.

## Considered Options

* Show every session the agent's pending wakes across all its conversations, and let the agent cancel its own wake with a reason
* Show the pending wakes, and leave cancelling to the operator
* Neither for now: run #140 as it is and measure whether agents need it

## Decision Outcome

Chosen option: the first. Will chose it (2026-11-26) from Claude's recommendation, while the Kubernetes deployment was being designed. Claude's reasoning was that this folds the ledger's two jobs into the wake queue Hearth already has, so a promise needs no mechanism of its own. A wake carries the promise. The agent sees the promise at the start of every session. When the agent drops the promise, the cancel records why.

* The session-start hook lists the agent's pending wakes, in all its conversations, with each one's conversation, note and due time.
* The agent can cancel a pending wake. Every cancel, the operator's included, carries a reason and who cancelled it.

### Consequences

* Good, because an intention, an alarm and a wait are now one thing to the agent.
* Good, because a request between two agents is visible on both sides without a protocol for it. The asker sets a wake to check for the reply, the receiver gets a wake from the message, and each agent sees its own at its next session.
* Bad, because the list can grow long for a busy agent and takes room in every session's context. The hook limits what it shows and says how many it left out.
* Bad, because nothing makes an agent set a wake in the first place. Whether agents do is something to measure.

### Confirmation

[Plugin](../interfaces/PLUGIN.md): every session starts by showing the agent its pending wakes, and unreadable wakes are reported, never shown as none. [Wake](../primitives/WAKE.md): a cancel carries a reason and who cancelled it. Tests name both invariants.
