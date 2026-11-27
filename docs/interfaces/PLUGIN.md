# Plugin

Hearth's own Claude Code plugin, loaded into every session Hearth launches, for turns and for interactive sessions alike. It needs no install step. Its session hooks are also written into each agent's configuration directory when the agent is installed, so that a session started there without Hearth is recorded too; that copy records and tells the agent nothing. On the other side is the agent in its session, and the person at the keyboard when there is one.

The hooks tell Hearth which sessions are open and tell the agent that Hearth exists. The commands are thin: each runs the [operator's commands](COMMANDS.md).

## What passes

| Hook or command | What it does |
|---|---|
| Session start | Records the session as open, or, for a turn the gateway is running, records the session as that turn's conversation. Tells the agent that Hearth exists, its agent name, this conversation's id, how to wait, and its pending wakes |
| Session end | Clears the record of the session |
| Wake command | Sets a wake for this conversation after a delay or at a time |
| Status command | Shows [status](STATUS.md) |
| Agents command | Lists the registered agents |

## Invariants

- **Every session of an agent starts by showing the agent its own pending wakes, in all of its conversations, each with its conversation, its note and when it is due.** Wakes that can't be read are reported as unreadable, never shown as none.
- **The agent is told, at the start of every session, to wait by setting a wake for this conversation and ending its turn, never by holding a turn open.**
- **A session Hearth launched is recorded when it starts and cleared when it ends, and a record whose process has gone is not an open session.**
- A turn the gateway runs is never recorded as open.
- The hooks work whether or not the gateway is running, and never block or fail a session.
- A command does only what the operator's command of the same name does, with the current conversation as its default.
- The agent is told the id of the conversation it is in, so a wake it sets comes back to that conversation and not to a new one.
