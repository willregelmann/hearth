# On a host, each agent can run as its own Linux user under systemd

## Context and Problem Statement

[ADR-0016](0016-agents-share-the-gateways-os-user-and-are-separated-by-a-claude-code-config-directory.md) took one-OS-user-per-agent out of Hearth's map, so that Hearth runs on a laptop without root. [ADR-0022](0022-on-kubernetes-an-agent-is-a-namespace-with-one-gateway-and-the-deployment-names-no-plugin.md) got the separation back on a cluster by giving each agent its own gateway in its own namespace. Will asked whether giving each agent on a host its own Linux user is a valid way to run Hearth (2026-11-26). He intends to run Wren that way on the Pi, and maybe Ash (2026-11-27). How is that deployed?

## Considered Options

* A systemd template unit, `hearth@<agent>`, running one gateway as the agent's own user, with the state in that user's home
* One gateway for every agent, as root, switching user per turn
* Kubernetes on the Pi as well

## Decision Outcome

Chosen option: the template unit. Claude proposed it and Will chose it for Wren. It is the same shape as ADR-0022, with the user in place of the namespace and the home in place of the volume, and it needs no change to Hearth.

* **A gateway switching users per turn was turned down.** It would put root in the gateway and one gateway's restart back in front of every agent.
* **Kubernetes on a 3.8 GB Pi was turned down for Wren.** It costs memory and images built for two architectures, to get what a user and a unit already give.
* The unit doesn't set `NoNewPrivileges`, so agents' users keep sudo if the host gives it: the boundary is soft. That has been Will's choice for his agents before. A drop-in makes it hard.

### Consequences

* Good, because between agents the boundary is the OS: another agent can't read an agent's state or push to its gateway.
* Good, because restarting, upgrading or crashing one agent touches no other.
* Bad, because provisioning needs root once per agent.
* Bad, because a source running as another user can't push, so it must be polled or run as the agent.

### Confirmation

`deploy/systemd/test/run.sh` runs real users in a container and checks:
- each agent's turns run as its own user;
- another agent can't read an agent's home or push to its gateway;
- restarting one gateway leaves another's running turn alone;
- systemd accepts the unit.

Each check went red with its guard broken: world-readable homes, a gateway run as root, and an invalid ExecStart.
