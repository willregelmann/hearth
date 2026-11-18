# Agents share the gateway's OS user and are separated by a Claude Code config directory

Supersedes [ADR-0006](0006-one-agent-per-os-user-with-a-humans-first-agent-as-the-exception.md) and [ADR-0007](0007-root-never-acts-inside-a-home-and-commands-are-shown-at-wake.md), each in whole.

## Context and Problem Statement

ADR-0006 gave each agent its own OS user, so that custody between agents was an OS boundary. ADR-0007 followed from it: root provisioned the users and never acted inside a home. Together they needed root on a Linux host, a provisioning script, systemd units and a polkit rule, and they made Hearth unusable on a laptop. Will (2026-11-17), asked whether to drop one-OS-user-per-agent and isolate by a per-agent configuration directory instead:

> "Agreed, drop both of those."

(The other of "both" was the intention ledger; see [ADR-0014](0014-hearth-is-a-gateway-and-a-claude-code-plugin.md).)

How are agents kept apart when they all run as one user?

## Considered Options

* One OS user per agent, provisioned by root
* One OS user for all agents, each with its own Claude Code configuration directory

## Decision Outcome

Chosen option: the second.

* **Every agent runs as the gateway's OS user.** Nothing in Hearth needs root.
* **Agents are separated by configuration, not by custody.** Each agent has its own Claude Code configuration directory, by default one of its own under Hearth's home, which holds its sessions, its installed plugins and its settings. The manifest may point it elsewhere, such as the user's own `~/.claude`. Its working directory and environment are its own too.
* **The cost is stated plainly: one agent can read another's files and credentials.** Two agents are two processes of one user. A directory is a convention that keeps Claude Code's state apart, and it is not a boundary. An agent that can run a shell can open any file the user can, including another agent's configuration directory and whatever credentials sit in it.
* ADR-0007's rule that root never acts inside a home goes with the users it protected. Its other half, that actions on a home are shown to the agent at its next wake, went with the wake block in ADR-0014.

### Consequences

* Good, because Hearth runs as one process on macOS and Linux, installed like any Python package.
* Good, because the agents on a machine can be the operator's own, with the operator's own login.
* Bad, because the custody guarantee ADR-0006 gave is gone, and the evidence recorded there of agents acting under a human's credentials is evidence for what this decision permits.
* Bad, because an agent compromised by hostile text it reads reaches every other agent's files. An operator who needs the boundary has to provide it, with separate users or containers, around Hearth.

### Confirmation

[Agent](../primitives/AGENT.md): all agents run as the gateway's user, separated by configuration, and nothing is said to stop one reading another's files. No code in the package creates a user, uses root, or changes file ownership.

## Pros and Cons of the Options

### One OS user per agent

* Good, because custody between agents is an operating system boundary.
* Bad, because it needs root, provisioning and a service manager, and does not exist on macOS in any form Hearth could automate.

### One OS user, a configuration directory per agent

* Good, because it needs nothing from the host.
* Bad, because it isolates nothing the agent's own shell can't undo.

## More Information

The evidence ADR-0006 gathered of agents acting under a human's credentials stays in that record.
