# Deliver

Putting a [wake](../primitives/WAKE.md) in front of its [agent](../primitives/AGENT.md): when a wake is due, Hearth runs one turn in the wake's [conversation](../primitives/CONVERSATION.md), with the agent's own configuration, and shows the turn what woke it. The wake counts as done only after that turn finishes.

What the agent does with a wake is the agent's judgment. That it is shown, in the right conversation, once, is fixed.

## Invariants

- **A wake reaches the conversation it names, without anyone having to open it, and is never delivered into a different one.**
- **At most one gateway delivers for a Hearth home at a time.** A second one refuses to start.
- A woken turn is shown each wake's source and note together, and is told when a wake may have been shown before and how late a wake is.
- A woken turn is told its reply text is not delivered to anyone.
- A turn runs with its agent's configuration directory, working directory, environment, model and declared plugins, and with no other agent's.
- A conversation that is deferred, delayed by a failure, or waiting on a not-before time is visible as such on [status](../interfaces/STATUS.md). Nothing waits silently.
- One conversation's failing, slow or deferred turn never holds up a wake in another.
- A turn started for a wake never waits for a person.
