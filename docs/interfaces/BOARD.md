# Board

The one surface the operator checks, and where the operator sees every agent on the host and talks to each one. What no agent can deliver, and what something outside the agents found, ends up here: undeliverable exits and reviews, ledgers left unattended, stalled intentions, refusals and holds.

No other household member is ever required to check it. Anything they must act on reaches them on a [channel](CHANNELS.md) they already use.

## What passes

| Entry | What it shows |
|---|---|
| Freshness | When the last full check ran, and of how many ledgers |
| Agents | Every declared agent, whether its process is running, and its [status](STATUS.md) as last read, with when |
| Unattended | A ledger whose sweep [Watch](../capabilities/WATCH.md) didn't see in time |
| Undeliverable | An exit or review that couldn't reach whoever it was for |
| Stalled | An intention put off repeatedly without new evidence, with each move's reason |
| Refused or held | A write or send that was refused or held, without quoting what was held |
| Custody unenforced | Owners that share an OS user, so their custody can't be enforced |

| Action | What it does |
|---|---|
| Talk | Opens the operator's thread with one agent, carried on a channel |
| Restart | Restarts one agent's process |

## Invariants

- **The board shows its own freshness.** A dead checker reads as stale, never as all clear.
- **Nothing that reaches the board is lost.** An entry stays until a person has seen it or what caused it is gone.
- **The operator talks to an agent on a channel, as a sender like any other.** The board never starts a turn or writes into a home.
- **What serves the board runs as neither root nor any agent.** Its reach is reading each agent's status, sending on channels as the operator, and restarting an agent's process. Anything that needs more is a [command](COMMANDS.md).
- Only the operator can open the board. No agent reaches it.
- Every declared agent is listed. One whose status can't be read shows as unreachable, never as idle and never left out.
- A restart is shown to the agent at its next [wake](../capabilities/WAKE.md), and restarting one agent never stops another.
- The board never quotes a fact outside its audience.
- The board is the end of the chain. Nothing escalates past it.
