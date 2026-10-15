# Channels

Where people and peers reach the agent and the agent reaches them: chat with the household, messages between agents, and the one directory of who the agent knows. On the other side are people, who use whatever channel they already use, and peers, who are other agents.

Every channel carries [threads](../primitives/THREAD.md), not separate minds: what arrives on one is the same agent's business as what arrives on another.

## What passes

| Thing | What it does |
|---|---|
| Inbound message | Starts or continues a thread, and starts a [wake](../capabilities/WAKE.md) |
| Outbound message | Passes on what the agent says, within each fact's audience |
| Delivery check | Says, for each channel, how a delivery is known to have been taken in |
| Directory | The one list of who the agent knows, each with a verified identity |

## Invariants

- **There is one directory.** Nothing else holds a list of peers. A name or a kind in the directory is a claim; only a verified identity makes someone known.
- **Every channel declares in advance how it knows a delivery was taken in.** A delivery that channel can't check is unmeasured, never counted as delivered.
- A message that names a state carries its version and a claim the receiver can recompute, and the receiver checks both against current state.
- A send outside a fact's audience is refused or held. The audience check covers everyone who can read the channel, and readers who can't be listed count as outside. A recipient not known to run Hearth counts as outside.
- A hold is shown on the [board](BOARD.md) and at the sender's next wake, and a refusal is an error the sending turn must handle. Neither ever quotes the fact it held back.
- A send to a thread that no longer exists fails visibly. It never lands silently in a new thread.
- Every message carries the label of its fact's audience with it.
