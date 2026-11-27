# Process liveness is read from /proc where it exists, and a zombie is not alive

## Context and Problem Statement

[ADR-0018](0018-hearth-learns-which-sessions-are-open-from-its-own-plugin-hooks.md) judges whether a recorded process is still the one recorded by its process id and its start time, and asked `ps` for the start time on both macOS and Linux. Run in a container, that breaks in two ways. Slim images have no `ps`, so no start time is recorded: an open-session record then stays open for as long as any process holds its id, and recovery won't kill a turn left running by a crashed gateway, because it requires a start time. And a process that has exited but hasn't been reaped, which is common when the gateway is the container's first process, still answers "exists". So a dead session counted as open forever.

## Considered Options

* Read the process's state and start time from `/proc` where it exists, and fall back to `ps` elsewhere
* Require `ps` in every image, and leave zombies to an init process

## Decision Outcome

Chosen option: the first. Decided by Claude while fixing the container findings of the #140 review (2026-11-26). It keeps working on a host that lacks `ps`. A zombie is a fact about the process, and Hearth should read it rather than depend on the image to prevent it. The deployment still runs an init process, so zombies don't pile up.

### Consequences

* Good, because no outside program is needed on Linux, and nothing blocks the gateway's event loop on a subprocess for every open session on every tick.
* Bad, because a start time recorded by one method doesn't compare with one recorded by the other. Records are tagged with their method, and a mismatch in method is treated as "can't tell", which counts as open.

### Confirmation

[Conversation](../primitives/CONVERSATION.md): a session counts as open only while its process lives, and a process that has exited but not been reaped is not alive. A test makes a zombie and checks it is not counted.
