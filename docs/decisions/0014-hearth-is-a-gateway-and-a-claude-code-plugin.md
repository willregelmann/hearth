# Hearth is a gateway and a Claude Code plugin; self, memory, intentions, threads, the board, watch and move leave it

Supersedes [ADR-0001](0001-focus-is-what-am-i-in-the-middle-of-and-what-would-close-it.md), [ADR-0002](0002-five-primitives-self-apart-from-memory-intention-replaces-commitment.md), [ADR-0003](0003-faculties-and-live-turns-to-home-one-self-many-turns-to-intention.md), [ADR-0004](0004-default-audience-is-the-household-narrowed-audience-includes-only-its-recorder.md), [ADR-0008](0008-the-board-is-the-operators-surface.md), [ADR-0012](0012-an-agents-claim-of-absence-names-where-it-looked.md) and [ADR-0013](0013-the-board-is-served-by-its-own-user-and-reaches-agents-only-through-status-and-channels.md), each in whole.

## Context and Problem Statement

Hearth was a harness for one continuous agent: it owned the agent's self, its memory, its intentions and its threads with audiences, ran each agent as its own OS user, served a web board for the operator, and watched and moved agents between hosts. Most of that was never built, and what was built tied Hearth to Linux, to root, to systemd and to two other projects. Will asked for something much smaller (2026-11-17):

> "I'd like to pare Hearth down to a bare minimum wrapper for Claude Code. We should support multiple agent registration, a wake API with support for arbitrary polling"

and, when asked what that meant:

> "To be clear, it's a gateway and a Claude Code plug-in with commands at minimum. Think Hermes Agent but extensible rather than featureful"

Asked whether to cut the intention ledger outright, along with the one-OS-user-per-agent rule (see [ADR-0016](0016-agents-share-the-gateways-os-user-and-are-separated-by-a-claude-code-config-directory.md)), he answered: "Agreed, drop both of those."

What is Hearth, and what is it no longer?

## Considered Options

* Keep Hearth as it was, and build the rest of the map
* A gateway and a Claude Code plugin, with everything else left to Claude Code and to plugins an agent declares
* Cut only the host-level machinery (users, root, systemd, board) and keep the intention ledger, self and memory

## Decision Outcome

Chosen option: the second, as the owner stated it.

* **Hearth is a gateway and a plugin.** The gateway is one long-running process that knows the registered agents and turns wakes into Claude Code turns in the right conversation. The plugin is loaded into every session Hearth launches and holds its hooks and commands.
* **Self, memory, intentions, threads with audiences, the board, watch and move leave Hearth.** An agent that wants a memory, a ledger of what it owes or a channel to people gets them from plugins it declares, as any Claude Code agent would. Hearth does not know which.
* **The intent changes.** The question Hearth keeps open is no longer what an agent is in the middle of, but whether each wake has reached a turn, exactly once, in the conversation it was for. The failure sentence follows: an accepted wake that is lost, runs twice or lands in the wrong conversation, or an agent that can't be reached because of which conversation it was in.
* **The primitives are Agent, Conversation and Wake.** A turn holds no rules of its own that a conversation and a wake don't already hold, so it is folded into them.
* **Rules that existed only to protect what leaves go with it.** The audience rules, the claim-of-absence rule, the custody of a home, and the board's separate user have nothing left to govern. The discipline behind the claim-of-absence rule is not judged wrong; Hearth no longer has a memory to hold it in.

### Consequences

* Good, because what Hearth promises is small enough to check: one question, three primitives.
* Good, because it runs anywhere Claude Code does, as one process under one user.
* Bad, because everything dropped here was a reasoned decision, and the people who relied on it lose it. Nothing in this repository now keeps an agent's own words about itself, an account of what it owes, or a privacy boundary between its conversations.
* Bad, because "the agent that can't be reached because of which conversation it was in" is now Hearth's whole account of continuity. Continuity of mind is left to Claude Code and to the agent's plugins.

### Confirmation

The [map](../INTENT.md) has no self, memory, intention, thread, board, watch or move, and its primitives are Agent, Conversation and Wake. No code in the package implements any of the removed things.

## Pros and Cons of the Options

### Keep Hearth as it was

* Good, because it was the design the project's agents had reviewed and agreed.
* Bad, because the owner asked for the opposite, and little of it ran.

### A gateway and a Claude Code plugin

* Good, because it is what the owner asked for.
* Good, because it can be extended by plugins and by sources, without Hearth changing.
* Bad, because it gives up the idea that the agent, not the conversation, is the unit.

### Cut only the host-level machinery

* Good, because it keeps the agent's identity and its account of what it owes.
* Bad, because the owner cut the intention ledger by name. TODO: no recorded reasoning on keeping self and memory beyond the owner's instruction that Hearth is a minimal wrapper.

## More Information

Written when the change was made, from the owner's messages quoted above. The weighing of the options before then was done in the planning conversation, which is not preserved here.
