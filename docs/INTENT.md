# Hearth

A gateway for Claude Code agents: it knows which agents exist and turns every wake into a turn in the right conversation.

Whenever something wants an agent's attention, Hearth keeps one question open: **has this wake reached a turn, exactly once, in the conversation it was for?**

An agent that runs only when a person types is half an agent. The alarm it set for tomorrow never fires, because the session that set it is closed. A message lands while a turn is running and is lost, or two turns write to one transcript. A restart swallows whatever was waiting. A poll finds the same thing every minute and wakes the agent every minute. The agent that waited by holding a turn open is still holding it.

Hearth is built on the idea that a wake is a promise, not a signal. It is written down before anyone is told it was accepted, it runs in one conversation, and it counts as done only when a turn has finished with it. Agents are registered with a manifest and run as Claude Code with exactly the plugins they declare. Wakes arrive by push or by being polled, from sources Hearth knows nothing about: it carries a label and a note, and the source's own tools show the rest. The agent can wait for real. It ends its turn with a wake set, and comes back in the same conversation when the time or the thing arrives, whether or not anyone has it open.

If an accepted wake is ever lost, runs twice, or lands in a conversation it was not for, or if an agent can't be reached because of which conversation it was in, Hearth has failed at the one thing it exists to do.
