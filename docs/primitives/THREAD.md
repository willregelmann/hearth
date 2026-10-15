# Thread

One exchange the agent holds with a counterparty: a person, a peer, or itself. A thread is the conversation as the agent knows it, wherever it happens. The same thread can move between channels, and two channels can carry pieces of one thread.

A thread is known by an explicit id that travels with its messages. Who it's with and what it's about can only suggest a thread; they never decide it. Joining two threads or splitting one is something the agent does on purpose, and leaves a record.

Every fact has an audience: who may hear it. A thread passes a fact on only to a counterparty that audience allows.

## Invariants

- **A thread passes on a fact only to a counterparty its audience allows.** The audience is set by the fact's subject, or narrowed by whoever records it, and a narrowing binds everyone downstream. It can be narrowed later, never widened except by the subject. A channel is never the subject.
- **Where no audience is set, the default is the household the fact came from, its people and the agents that serve them, not the thread it arrived in.** The default is written when the fact is recorded, so a fact with no audience at all can be found.
- When a fact's audience is narrowed to named people, the agent that recorded it is inside. Every other agent is outside unless one of those people says yes, and that yes covers one passing-on: it doesn't widen the fact.
- Either owner may widen a jointly held fact. The widening is recorded and the other owner told.
- A turn records at the narrowest audience of anything that entered its context. When those audiences don't overlap, what it records is for the agent alone, and its next [wake](../capabilities/WAKE.md) says so.
- **Every message carries its thread's id.** A message that arrives without one opens a new thread and says so to its sender, or joins the counterparty's one default thread. It never lands silently in a thread it wasn't sent to.
- A join or split is a new thread with its ancestry declared, never a quiet merge of two histories.
- A thread's end never closes an [intention](INTENTION.md). Intentions outlive the threads they started in.
