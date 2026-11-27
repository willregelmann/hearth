# A turn's session is mapped when it starts, and Hearth's session hooks live in each agent's configuration directory

Supersedes the third bullet of [ADR-0018](0018-hearth-learns-which-sessions-are-open-from-its-own-plugin-hooks.md)'s Decision Outcome, that the hooks cover only sessions that load Hearth's plugin. The rest of ADR-0018 stands.

## Context and Problem Statement

A review of #140 found two ways for a conversation to get two writers.

1. A name's first turn learned its session id only when the turn ended. The plugin tells the agent to wait by setting a wake for its session id. When the agent did that during the first turn, Hearth didn't know the id yet, so it made a second conversation for it. That conversation counted as free, so Hearth resumed the same session beside the running turn. When the first turn ended, recording the name's session failed on the duplicate, and the error was swallowed. The name's next wake then started a fresh session. A test reproduced it.
2. A session started with plain `claude` in an agent's configuration directory loads no Hearth plugin, so nothing records it as open, and a wake resumes it beside the person. On a container, where a person reaches the agent through `kubectl exec`, plain `claude` is the natural thing to type.

## Decision Drivers

* [Conversation](../primitives/CONVERSATION.md): a conversation never has two turns, and Hearth never resumes one a live session has open.
* Errors must fall toward "open" (ADR-0018).
* No reliance on where Claude Code keeps its transcripts, which it doesn't promise.

## Considered Options

For the first-turn session:

* The session-start hook of a gateway turn records the session as that turn's conversation
* Hearth picks the session id itself and passes it to Claude Code with `--session-id`
* The dispatcher refuses to start a turn for a session a live turn is in

For sessions started without Hearth:

* `hearth agent install` writes Hearth's session hooks into the agent's configuration directory
* Leave it to the operator to start sessions with `hearth session` (ADR-0018 as it stood)

## Decision Outcome

Chosen: the hook records the turn's session, and install writes the session hooks into the configuration directory. Decided by Claude, building the fix Will asked for (2026-11-26).

* The gateway passes each turn its turn id. The session-start hook of that turn writes the session onto the turn's conversation before the model runs, so the agent can't name the session before Hearth knows it. If the hook fails, the old record at the end of the turn still runs. A session that then turns up under two conversations is merged into the named one, and the merge is logged, never swallowed.
* Picking the id ourselves was turned down. A first turn that fails partway may or may not have created the session, and the retry would have to guess which, by looking where Claude Code keeps transcripts.
* The dispatcher check was turned down because the gateway learns a live turn's session only from the turn itself, which is the same gap.
* The hooks written into the configuration directory only record. They tell the agent nothing, so a session that also loads the plugin isn't told twice. Their command names the Hearth home and the agent, so they work without Hearth's environment.

### Consequences

* Good, because the agent can wait the way the plugin tells it to from its very first turn.
* Good, because every session in an agent's configuration directory is seen, however it was started.
* Bad, because the hook now writes Hearth's database, so a hook that can't reach it falls back to the late record.
* Bad, because the configuration directory's settings file is now partly Hearth's. Install rewrites only Hearth's own two hook entries and leaves the rest of the file as it found it.

### Confirmation

[Conversation](../primitives/CONVERSATION.md): a session is exactly one conversation; a name's first turn maps it as soon as its session starts; sessions started without Hearth are seen. Tests: a wake set during a name's first turn runs after it in the same session, and a session started with plain `claude` in the configuration directory defers a wake.
