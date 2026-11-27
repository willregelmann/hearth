# Telemetry is OpenTelemetry, configured only by OTEL_* variables, with the SDK optional

## Context and Problem Statement

Will wants OpenTelemetry to be first-class, exporting meaningful signals (2026-11-26). An earlier requirement asked for configuration through the standard `OTEL_*` environment variables (2026-10-18, hearth issue #120). Claude Code already exports what happens inside a turn: tokens, cost, tool calls and, in its beta, spans. What only Hearth can see is everything around a turn:
- a wake being accepted;
- a wake being held back: not yet due, deferred for an open session, or retrying after a failure;
- how late a wake was delivered;
- how each turn ended;
- whether each check succeeded.

What does Hearth export, how is it configured, and how do the two sides join?

## Decision Drivers

* [Telemetry](../interfaces/TELEMETRY.md): with no `OTEL_*` variable set, nothing changes.
* Nothing Hearth does may wait on, or fail because of, a collector.
* Hearth's package has no third-party runtime dependencies.
* A wake can be accepted by one gateway process and delivered by another, after a restart.

## Considered Options

For the dependency:

* The OpenTelemetry SDK as an optional extra, `hearth[otel]`, loaded only when the variables ask for it
* The SDK as a required dependency
* Hand-written OTLP

For joining a wake to its turn:

* The wake keeps the trace context it was accepted in, and the turn's span links to every wake it delivered
* The turn's span is a child of its first wake

## Decision Outcome

Chosen: the optional extra, and links from a stored trace context. Decided by Claude, building what Will asked for (2026-11-27).

* **The extra keeps the package free of dependencies for anyone who doesn't want telemetry.** When the variables ask for telemetry and the SDK is missing, that is reported on status and in the log, never silently absent.
* **Hand-written OTLP was turned down.** It would re-implement batching, retries and the exporters' own variables.
* **A turn delivers several wakes, often from different traces**, so it links to each rather than pretending to be the child of one. The wake's span context is stored with the wake, so the link holds across a restart.
* **The turn passes its own context to Claude Code as `TRACEPARENT`**, with the agent, conversation and turn as resource attributes, so Claude Code's spans and measurements join Hearth's.
  - An inherited `OTEL_SERVICE_NAME` is replaced by `claude-code`, so turns don't look like the gateway.
  - `hearth wake` sends any `TRACEPARENT` it runs under, so a wake an agent sets inside a turn is a child of that turn.
* **Only OTLP over HTTP/protobuf, or the console exporter, is supported.** Any other exporter or protocol is reported as a problem, never ignored.

### Consequences

* Good, because an intention can be followed from the turn that set it, to the wake, to the turn that came back to it.
* Good, because waiting, deferral and retrying are measurements, not only lines on status.
* Bad, because the gRPC exporter isn't supported, so a collector that only speaks gRPC needs its HTTP receiver enabled.

### Confirmation

`tests/test_telemetry.py` holds one test per invariant in [Telemetry](../interfaces/TELEMETRY.md). It reads spans and measurements from the SDK's in-memory exporters, with the gateway, its socket and its database real. Each test went red with the code it guards broken.
