# The board is served by its own user, and reaches agents only through status and channels

## Context and Problem Statement

Will wants a web page to manage the fleet: list the agents on a host and talk to each one (2026-10-29). Something long-running has to serve it, and it has to reach every agent. Who does that process run as, and how does it reach an agent without becoming a second way into the agent's attention?

## Decision Drivers

* [Commands](../interfaces/COMMANDS.md): inside a tenant's home, root neither reads nor writes (ADR-0007).
* [Home](../primitives/HOME.md): at most one agent per OS user, so custody between agents is an OS boundary (ADR-0006).
* The process serving the board is the one place where text from every agent, and from everyone who messages them, is parsed and shown.
* A [wake](../capabilities/WAKE.md) is the only start of a turn, and what reaches an agent's attention is recorded with who sent it.

## Considered Options

* Served as root, reaching into each home directly
* Served as its own user, reading each agent's [status](../interfaces/STATUS.md) and talking on [channels](../interfaces/CHANNELS.md)
* Served as the operator's own user

## Decision Outcome

Chosen option: the second. Proposed by Claude and accepted by Will, who asked for the map change after weighing root (2026-10-29).

* The board's process runs as a user of its own: neither root nor any agent. A bug in it, or hostile text an agent or a sender got into what it reads, reaches what that user can reach, not every home on the host.
* It reaches an agent two ways, kept apart. Status is read-only and served by the agent's own process; it never starts a turn. Talking is a message on a channel, sent as the operator, so it wakes the agent like any other message and is recorded with who sent it.
* It can restart an agent's process, and nothing else that needs privilege. Provisioning, moves, loans and manifests stay [commands](../interfaces/COMMANDS.md) that the operator runs as root.

### Consequences

* Good, because ADR-0007 stays a fact about the host rather than a promise about the board's code.
* Good, because an agent never depends on the board: a dead board is a stale board, and the agents run on.
* Bad, because the board can't provision or change a manifest. Doing that from the page later needs a separate privileged helper that accepts only those commands, each still shown at the agent's next wake.
* Bad, because the board's user needs a read grant on each agent's status, set up when the agent is provisioned.

### Confirmation

[Board](../interfaces/BOARD.md): what serves it runs as neither root nor any agent, and talks to agents on channels. [Status](../interfaces/STATUS.md): it reports and never starts a turn. [Watch](../capabilities/WATCH.md): it reads only status.

## Pros and Cons of the Options

### Served as root

* Good, because it needs no grants and no helper.
* Bad, because a compromise of the page is a compromise of every home, which undoes ADR-0006's boundary.
* Bad, because ADR-0007 would hold only as long as the board's code chose to keep it.

### Served as the operator's own user

* Good, because the operator already has a read grant on each home.
* Bad, because the operator's user holds the operator's own credentials, which every agent's text would then be parsed next to.

## More Information

How it's built today, which the map leaves open:

* Browser to the board's process: HTTP and JSON, with server-sent events for live updates, on a Unix socket behind a proxy that does the operator's login.
* The board's process to each agent's status: gRPC on a Unix socket the agent's host process serves as the agent, with a group grant for the board's user.
* Talking: the operator's own Front Desk identity.
* Restart: systemd, through a polkit rule limited to the agents' host units.
