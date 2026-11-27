# Checks

What a source ships so that Hearth can [poll](../capabilities/POLL.md) it: a command that prints what is waiting. On the other side is whatever program the [agent's](../primitives/AGENT.md) manifest names, which knows its source and nothing about Hearth.

A check has a name, a command and an interval. Hearth runs it in the agent's working directory with the agent's environment, under a timeout.

## What passes

| Direction | What crosses |
|---|---|
| Out | The agent's environment and working directory, and nothing on standard input |
| In | Zero or more lines, each a JSON object naming a conversation and a key, with an optional note |
| In | The exit status |

Each line is one [wake](../primitives/WAKE.md) whose source is the check's name.

## Invariants

- **A check succeeds only when it exits zero and every line it printed is understood. Anything else is a failure, never an empty result.**
- A line that isn't a JSON object, or lacks a conversation or a key, fails the whole run. Part of an output is never used.
- A check that times out is killed together with everything it started.
- A check's output is never written to Hearth's logs. What is kept is its keys, as the record of what it last printed, and each note, as the note of the wake it raised.
- A check runs as the same user as the agent's turns, with no more access than a turn has.
