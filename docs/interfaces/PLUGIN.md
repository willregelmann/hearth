# Plugin

Hearth's own Claude Code plugin, loaded into every session Hearth launches, for turns and for interactive sessions alike. It needs no install step. On the other side is the agent in its session, and the person at the keyboard when there is one.

The hooks tell Hearth which sessions are open and tell the agent that Hearth exists. The commands are thin: each runs the [operator's commands](COMMANDS.md).

## What passes

| Hook or command | What it does |
|---|---|
| Session start | Records the session as open, unless it is a turn the gateway is running. Tells the agent that Hearth exists, its agent name, this conversation's id, and how to wait |
| Session end | Clears the record of the session |
| Wake command | Sets a wake for this conversation after a delay or at a time |
| Status command | Shows [status](STATUS.md) |
| Agents command | Lists the registered agents |

## Invariants

- **The agent is told, at the start of every session, to wait by setting a wake for this conversation and ending its turn, never by holding a turn open.**
- **A session Hearth launched is recorded when it starts and cleared when it ends, and a record whose process has gone is not an open session.**
- A turn the gateway runs is never recorded as open.
- The hooks work whether or not the gateway is running, and never block or fail a session.
- A command does only what the operator's command of the same name does, with the current conversation as its default.
- The agent is told the id of the conversation it is in, so a wake it sets comes back to that conversation and not to a new one.
