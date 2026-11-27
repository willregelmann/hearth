# Conversation

A Claude Code session of one [agent](AGENT.md), which is where a [wake](WAKE.md) lands. A wake names its conversation either by session id or by a name. A name is the agent's own label for a session: its first turn starts a fresh session, and from then on the name stands for that session.

The conversation is the unit of exclusion. Turns happen in it one at a time, and only while no person has it open. A turn is not a thing of its own: it is one run of Claude Code in a conversation, and it leaves a record.

## Invariants

- **A conversation never has two turns running at once.** A wake for a conversation that is mid-turn runs after that turn, never beside it. Different conversations run in parallel.
- **Hearth never resumes a conversation that a live interactive session has open.** Such a wake is deferred and runs once the session closes. Where it can't tell, it treats the conversation as open, because a wrong "open" only delays a turn.
- Hearth knows what is open from sessions it sees start and end, including sessions started in an agent's configuration directory without Hearth. A session counts as open only while its process lives, and a process that has exited but not been reaped is not alive. Turns the gateway runs itself are never counted. This holds on every supported operating system.
- A reference resolves in this order: a name the agent already maps to a session; a string shaped like a session id, which is that session; any other string, which is a new name.
- **A session is exactly one conversation, whether a wake names it by its name or by its session id.** A wake the agent sets during a turn, naming the session it is in, lands in that turn's conversation and runs after it.
- A name maps to at most one session. Once mapped it always resumes that session. A name's first turn maps it as soon as its session starts, before the agent can act in it.
- Every turn leaves exactly one record: agent, conversation, session id, what woke it, when it started and ended, and how it ended. A turn that failed, timed out or was interrupted leaves one too. A record never holds prompt or reply text.
- A turn that outlives its timeout is killed together with everything it started.
