# Wake

The start of every turn the agent takes, however it was started: a message, a [clock](../interfaces/CLOCK.md) firing, or a reply it was waiting for. Wake puts in front of the agent what it's in the middle of, before it does anything else. That means its open [intentions](../primitives/INTENTION.md), what changed in its [home](../primitives/HOME.md) since its last turn, and which of its turns are live.

A wake comes back to the [thread](../primitives/THREAD.md) it's for, whether or not anyone has that conversation open. The agent waits by ending its turn with a wake set: for a time, for an answer, for a peer. The wake brings it back in the same conversation.

What the agent does with any of it is the agent's judgment. That it's shown is fixed.

## Invariants

- **Every turn starts by showing the agent what it's in the middle of.** No route into a turn skips it, and a turn that couldn't build the view says so before doing anything else.
- **What changed in the agent's home since its last turn is shown as one block, before the turn writes anything.** It covers every action taken through [commands](../interfaces/COMMANDS.md), every revoked loan, and every faculty now absent.
- Every open intention that's due is shown. One the sweep couldn't see is shown as an error, never left out.
- The live-turns view is shown beside the intentions, with what it can't prove: an empty list doesn't mean no other turn is running.
- **A wake resumes the thread it's for, whether or not anyone has that conversation open.** A wake the agent set for itself comes back in the thread that set it, never in a fresh one.
- A thread never has two turns writing to it at once. A wake for a thread that's mid-turn, or open in a live session, is taken up there or runs after it, never beside it.
- What woke a turn counts as taken in only once that turn has finished. A turn that fails leaves it pending and is tried again, without waiting for another message or a restart.
- A wake outlives a restart. One still pending when Hearth stopped, even in the middle of its turn, runs once Hearth is back.
- Wake reads; it never changes an intention or closes one on the agent's behalf.
