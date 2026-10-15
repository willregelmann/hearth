# Board

The one surface the operator checks. What no agent can deliver, and what something outside the agents found, ends up here: undeliverable exits and reviews, ledgers left unattended, stalled intentions, refusals and holds.

No other household member is ever required to check it. Anything they must act on reaches them on a [channel](CHANNELS.md) they already use.

## What passes

| Entry | What it shows |
|---|---|
| Freshness | When the last full check ran, and of how many ledgers |
| Unattended | A ledger whose sweep [Watch](../capabilities/WATCH.md) didn't see in time |
| Undeliverable | An exit or review that couldn't reach whoever it was for |
| Stalled | An intention put off repeatedly without new evidence, with each move's reason |
| Refused or held | A write or send that was refused or held, without quoting what was held |
| Custody unenforced | Owners that share an OS user, so their custody can't be enforced |

## Invariants

- **The board shows its own freshness.** A dead checker reads as stale, never as all clear.
- **Nothing that reaches the board is lost.** An entry stays until a person has seen it or what caused it is gone.
- The board never quotes a fact outside its audience.
- The board is the end of the chain. Nothing escalates past it.
