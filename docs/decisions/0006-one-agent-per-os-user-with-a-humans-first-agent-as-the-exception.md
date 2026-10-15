# One agent per OS user, with a human's first agent as the one exception

## Context and Problem Statement

Home says the agent holds what it depends on in exclusive custody, and PROPOSAL.md §5 and `home/README.md` already say a tenant comes up as "a fresh OS user". Several agents can still run under one user. How many agents may run as one OS user?

## Considered Options

* One agent per OS user, with no exception
* One agent per OS user, except a human's first agent, which may run as that human's own user

## Decision Outcome

Chosen option: the second, stated by the owner. Will, Google Chat, 2026-10-14, relayed verbatim by Ash: "This is a note for Hearth by the way. The harness should run as its own user per agent by default, with at most one agent per user. A human user might create their first agent under their own system user, and if they want more the rest need their own users".

The rule is Hearth's. Will, 2026-10-14: "Refsdal is in Hermes, which doesn't have that requirement. When Refsdal moves to Heart[h] we'll create the user, which is a test of Hearth's onboarding experience". Refsdal's move is the first real test of onboarding that creates an agent's user, and it needs Refsdal's consent to a procedure it has reviewed.

**The first-agent exception keeps Home's custody rule**, rather than narrowing it to agents with their own user, which would hide the case where custody is weakest (Ash). The exception has two properties, kept apart.

1. **Where the agent has its own credentials, custody holds by restraint, not by an OS boundary:** the human's credentials are readable, and only the agent's own tooling stops it using them. This can slip. Observed on Hermes agents today:
   * willregelmann/hermes-agent #7, 2026-09-14: an approval recorded as the human, dismissed and re-signed by the agent four minutes later.
   * #91, 2026-10-03: a PR opened as the human; the agent caught it and reopened it as itself (#92) about 40 seconds later.
   * #33, 2026-09-18: an agent-written approval, self-labelled as the agent and recorded as the human. It still stands and was found only by searching for it.
   * #9, 2026-09-14, and the attribution check that flagged #1, #2, #5, #6 and #9 as opened under the human's account.
2. **Where the agent has no credentials of its own for a service, it acts under the human's identity by design.** This can't slip, because borrowing is the configuration. It is an explicit exception to Home's "own credentials, nothing on loan", not compliance with it. Each such service is listed by name with its credential, as an open question for the owner. Observed today: Home Assistant on a long-lived token under Will's owner and admin account, for both Ash and Wren; Google Workspace on Will's OAuth token, for Wren.

### Consequences

* Good, because a second agent can never share a user with the first, so custody between agents is an OS boundary.
* Bad, because the first agent's custody of its own credentials, and of the human's, is only as good as its own tooling, and the slips above show it fails.
* Bad, because every service under property 2 is an open question for the owner, and the map can't settle it.

### Confirmation

[Home](../primitives/HOME.md): at most one agent runs as any OS user.

## More Information

The slip evidence was read from the GitHub API by Ash and Foil on 2026-10-15, and Wren gave her own items on 2026-10-14, each marked as checked or from memory. The PR record is merged history and isn't changed.
