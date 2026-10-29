# Status

What each agent's running process reports about itself to something outside it: the [board](BOARD.md) and [Watch](../capabilities/WATCH.md). On the other side is whatever serves the board. Status is the agent's view of itself running, from its [home](../primitives/HOME.md), shown outside.

## What passes

| Report | What it shows |
|---|---|
| Live turns | Which of the agent's turns are running, and which [thread](../primitives/THREAD.md) each is in |
| Faculties | Which declared faculties are present, and which are absent |
| Pending wakes | [Wakes](../capabilities/WAKE.md) waiting to run, with any that failed and when each is tried again |
| Last sweep | The sweep's own record of finishing |
| Recent turns | What started each recent turn and how it ended, without what was said in it |

## Invariants

- **Status reports. It never starts a turn, sends a message or changes anything in the home.** Whatever is meant for the agent's attention reaches it on a [channel](CHANNELS.md).
- **The agent runs the same whether or not anything reads its status.** Status is served by the agent's own process, as the agent, and nothing the agent does waits on a reader.
- Status never shows what the agent remembers or what was said in a thread, and never quotes a fact outside its audience.
- No other agent can read an agent's status.
- What's read here is the agent's own account. It can't change what the board shows about another agent, or about the board itself.
