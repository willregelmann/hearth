# An agent's turns are permissive unless its manifest says otherwise

## Context and Problem Statement

A turn Hearth runs has nobody to answer a permission prompt. [Deliver](../capabilities/DELIVER.md) already says a turn started for a wake never waits for a person. Without a permission mode, Claude Code blocks such a turn's tool calls instead: the first real turn traced through Hearth's telemetry showed `claude_code.tool.blocked_on_user` spans for each one. What permission mode do turns run with?

## Considered Options

* Permissive (`bypassPermissions`) unless the manifest names another mode
* Claude Code's own default unless the manifest names one
* No default: a manifest must name a mode

## Decision Outcome

Chosen option: the first, Will's choice (2026-11-27): "Let's be permissive by default."

* The mode is a manifest setting, `permission_mode`, one of the modes Claude Code accepts. A manifest that also passes one in `claude_args` is refused, so there's never a question of which won.
* Interactive sessions opened as the agent use the same mode, because a session runs exactly as the agent's turns do.

### Consequences

* Good, because unattended turns can act, which is what an agent woken by a wake is for.
* Bad, because a turn can do anything its OS user can. The boundary is the user, the container or the volume the agent runs in, never the prompt. Running an agent as root makes Claude Code refuse the mode, and the turn fails visibly.

### Confirmation

[Agent](../primitives/AGENT.md): turns are permissive unless the manifest says otherwise. Tests: a turn and a session both get `--permission-mode bypassPermissions` by default; a named mode is used; a manifest naming a mode twice is refused.
