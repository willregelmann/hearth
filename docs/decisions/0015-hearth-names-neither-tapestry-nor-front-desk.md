# Hearth names neither Tapestry nor Front Desk: sources reach it by push or by being polled

Supersedes [ADR-0009](0009-tapestry-and-front-desk-are-pinned-imports-front-desk-carries-agent-traffic-now.md) and [ADR-0011](0011-a-plugin-pin-has-two-sources-of-truth-and-the-installed-one-wins-at-run-time.md), each in whole, and the two clauses of [ADR-0005](0005-the-map-names-no-product.md) named under its title. The rest of ADR-0005 stands: the map names no product.

## Context and Problem Statement

ADR-0009 made Tapestry and Front Desk pinned imports of Hearth, with Front Desk carrying agent traffic and Hearth's host implementing Front Desk's `Host` protocol. ADR-0011 recorded how those pins were read at run time. Hearth's code and its container tests were bound to both packages' interfaces. Will (2026-11-17), asked whether Hearth could stay independent of them:

> "Can front desk push rather than the gateway polling? I'd love to have first-class support for both"

> "Okay, as long as we can decouple front desk and tapestry from hearth. I'll use them together in practice, but the hearth harness doesn't need to know about them"

> "Why do we need an adapter? If hearth supports polling, can't we poll the frontdesk gateway?"

How does Hearth stay decoupled from them and still work with them?

## Decision Drivers

* A source that wants low latency should be able to have it.
* A source that doesn't push should still be reachable, without Hearth shipping code for it.
* Hearth should have no runtime dependency on anything but the standard library, and Claude Code.

## Considered Options

* Keep both as pinned imports
* An adapter in Hearth for each source, or a supervised listener Hearth runs on a source's behalf
* No adapter: sources push to Hearth, or are polled through a command the source ships

## Decision Outcome

Chosen option: the third, as the owner reasoned it.

* **Hearth names neither Tapestry nor Front Desk** in its code, its package metadata, its map or its README. They are ordinary Claude Code plugins an agent may declare in its manifest, and ordinary sources of wakes.
* **A source that wants low latency pushes** a wake to the gateway ([Push](../interfaces/PUSH.md)). **Anything else is polled** through a [check](../interfaces/CHECKS.md): a command the source ships, which Hearth runs on an interval.
* **There is no adapter and no supervised-listener extension point.** A listener a source needs, it runs itself.
* The pins and their run-time resolution are gone, because the dependencies are.
* **ADR-0005's list of what Hearth uses today, and its Confirmation's statement that no map file names Claude Code, are superseded.** The list named Front Desk, Google Chat and Tapestry. The map now names Claude Code, and only Claude Code, in [its own file](../interfaces/CLAUDE-CODE.md): Hearth is a way of running it, and a map that could not name it could not say what Hearth asks of it. The rest of ADR-0005 stands.

### Consequences

* Good, because Hearth has no third-party runtime dependency.
* Good, because either source can be replaced, or used without the other, without a change to Hearth.
* Bad, because a source that wants to push has to know Hearth's socket, and one that is polled has to ship a command with Hearth's output format.
* Bad, because latency for a polled source is its interval.
* Bad, because an extension that needs a long-lived process next to the gateway has no help from Hearth. TODO: no recorded case of a source that cannot push or be polled.

### Confirmation

No file in the package, its metadata or its documentation outside `docs/decisions/` and `discussions/` names either product.

## Pros and Cons of the Options

### Keep both as pinned imports

* Good, because nothing new is built.
* Bad, because Hearth could not run, or be tested, without both.

### An adapter or a supervised listener

* Good, because Hearth could give a source lower latency without the source knowing its socket.
* Bad, because the owner asked why it was needed and the answer was that polling covers it: one more extension point, with its own failure modes, for what a command and an interval already do.

### No adapter

* Good, because there are two routes into a wake and both end in the same queue, under the same rules.

## More Information

Both products remain the owner's choice for their own use alongside Hearth. This record decides only what Hearth knows.
