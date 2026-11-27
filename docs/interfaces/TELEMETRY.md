# Telemetry

What the gateway exports about itself through OpenTelemetry: traces, metrics and logs, to whatever collector the standard `OTEL_*` variables name. On the other side is the operator's observability stack. It sees what only Hearth can: wakes being accepted, held back and delivered, and the turns and checks that follow. Claude Code exports its own telemetry about what happens inside a turn, and the two join on the agent and the turn.

## What passes

| Signal | What it shows |
|---|---|
| A wake's span | A [wake](../primitives/WAKE.md) accepted, by push or by [poll](../capabilities/POLL.md), as a child of the trace that raised it when the raiser named one |
| A turn's span | One turn: its agent, [conversation](../primitives/CONVERSATION.md), session, what woke it and how it ended, linked to the span of every wake it delivered |
| A check's span | One run of a [check](CHECKS.md): whether it succeeded, and how many wakes it raised |
| Wake measurements | Wakes accepted, by source and route; wakes waiting, by why they wait (not yet due, deferred, retrying); how late each was delivered |
| Turn measurements | Turns by outcome, and how long they took |
| Check measurements | Check runs by outcome |
| Session measurements | Sessions a person has open |
| Logs | The gateway's own log, tied to the trace it was written in |

## Invariants

- **Telemetry is configured only by the standard `OTEL_*` variables. With none set, Hearth exports nothing and behaves exactly the same.**
- **Nothing Hearth does waits on telemetry or fails because of it.** A collector that is slow, down or refusing costs signals, never a wake or a turn, and stopping the gateway waits on it only for a bounded time.
- **Telemetry never carries a prompt, a reply, a wake's note or a check's output.**
- **A turn's span links to the span of every wake it delivered, even when the gateway restarted in between.**
- A wake an agent sets from inside a turn is a child of that turn's trace, so an intention can be traced back to the turn that made it.
- Every measurement and span carries the agent it is about, so agents are always separate series.
- Claude Code's telemetry for a turn carries the same agent and turn, and that turn's trace context, so the two can be joined.
- Telemetry that was asked for but can't be produced, such as when the exporter isn't installed, is reported on [status](STATUS.md) and in the log, never silently absent.
