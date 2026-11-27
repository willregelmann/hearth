# Claude Code

What Hearth asks of Claude Code, the one program it wraps and the only product the map names. This file holds what Hearth requires of each run and what it assumes in return.

## What passes

| Direction | What crosses |
|---|---|
| Out | One non-interactive run per turn, resumed by session id when the conversation has one, with the agent's configuration directory, working directory, environment, model, permission mode and plugin directories, and Hearth's own plugin |
| Out | The turn's identity for Claude Code's own [telemetry](TELEMETRY.md): the agent, the conversation and the turn as resource attributes, and the turn's trace context |
| Out | Nothing on standard input |
| In | A result that reports the session id and whether the run failed |
| In | The plugin hooks Hearth's [plugin](PLUGIN.md) relies on, fired for resumed runs as for fresh ones |

## Invariants

- **A turn's reply text is never written to a log or kept.**
- **A turn runs in its own process group, and a timeout kills the whole group.**
- A run that can't start, exits non-zero, reports an error, or prints something that is not a result is a failed turn, never a finished one.
- The location of the Claude Code program is configuration, so that something else can stand in for it.
- Hearth passes the agent's declared plugins and its own, and disables any other plugin installed in the agent's configuration directory.
