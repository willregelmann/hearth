# On Kubernetes, an agent is a namespace with one gateway, and Hearth's deployment names no plugin

## Context and Problem Statement

Will wants Hearth portable enough to run in the cloud, and Kubernetes' primitives line up with it
(2026-11-26). #140's gateway can serve many agents from one process, all as its OS user
([ADR-0016](0016-agents-share-the-gateways-os-user-and-are-separated-by-a-claude-code-config-directory.md)).
How should agents map onto a cluster, and where does the wiring to other services live?

## Decision Drivers

* [Agent](../primitives/AGENT.md): adding, removing or reloading one agent never disturbs another.
* [Deliver](../capabilities/DELIVER.md): at most one gateway delivers for a Hearth home at a time.
* On the agents' earlier harness, restarting one shared gateway restarted every agent it served, without their consent.
* [ADR-0015](0015-hearth-names-neither-tapestry-nor-front-desk.md): Hearth names neither Tapestry nor Front Desk.

## Considered Options

For the topology:

* One namespace and one gateway StatefulSet per agent
* One gateway pod for every agent, as on a single host
* A pod per conversation, created when a wake arrives

For the wiring:

* Hearth ships a generic gateway image and per-agent base; a composition adds plugins and services
* Hearth's deployment includes the memory server and the message desk

## Decision Outcome

Chosen: a namespace and a single-replica gateway StatefulSet per agent, with a generic image and
base. Will agreed to the topology after comparing the designs (2026-11-26). Claude proposed it,
reasoning that the agent, not the conversation, should be the unit the cluster knows. Its pieces:

* **The agent's volume is its whole home** and is mounted by its gateway alone. That gives the
  separation between agents that ADR-0016 gave up, on a cluster, without changing Hearth.
* **A pod per conversation was rejected.** Hearth's own records of the earlier harness show its
  failures came from one agent split into many sessions. Pod start-up would be paid on every wake,
  and the many pods would share one volume.
* **One gateway for every agent was rejected** because it rebuilds the shared-restart failure.
* **Commands run in the pod.** `kubectl exec` replaces provisioning, and interactive sessions run
  there too, so the open-session check sees them.
* **Nothing in `deploy/` names a plugin.** Front Desk, Tapestry and anything else an agent uses
  are added by an image built `FROM` the gateway image and an overlay of the base, kept with the
  deployment that composes them.

### Consequences

* Good, because one agent's restart, upgrade or crash touches no other agent.
* Good, because Hearth runs unchanged: a container is one more host.
* Bad, because each agent has an always-running pod, idle or not.
* Bad, because Hearth's push socket is reachable only inside the pod. A source in another pod raises
  wakes by being polled, or by a pusher placed beside the gateway.

### Confirmation

`deploy/test/kind-e2e.sh` checks in a real pod that:
- a wake reaches its conversation;
- a wake survives the pod being force-killed mid-turn;
- a not-before wake never fires early across a reschedule;
- a second gateway refuses to start.

A review checks that `deploy/` names no plugin.
