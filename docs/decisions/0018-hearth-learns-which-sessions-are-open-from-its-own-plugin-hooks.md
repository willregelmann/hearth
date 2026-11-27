# Hearth learns which sessions are open from its own plugin's hooks

The third bullet of the Decision Outcome, that the hooks cover only sessions that load Hearth's plugin, superseded by ADR-0020.

## Context and Problem Statement

A wake must never resume a conversation a person has open, because that is two writers on one transcript. The previous design learned what was open from another project's session records, and from Linux's `/proc` to find which processes were Claude Code. Neither is available now: Hearth names no other project ([ADR-0015](0015-hearth-names-neither-tapestry-nor-front-desk.md)), and `/proc` does not exist on macOS. How does Hearth know which sessions are open?

## Decision Drivers

* A wrong "open" only delays a turn, and a wrong "closed" corrupts a transcript, so errors must fall toward open.
* It must work the same on macOS and Linux.
* Turns the gateway runs itself must not count as someone having the conversation open.

## Considered Options

* Inspect the operating system's process table for Claude Code processes and match them to sessions
* Ask Claude Code for its open sessions
* Hearth's plugin hooks record a session when it starts and clear it when it ends

## Decision Outcome

Chosen option: the third.

* **The plugin's session-start hook records the session**, with the process that is running it and when that process started, unless the session is a turn the gateway is running (the gateway marks its own turns in the environment).
* **The session-end hook clears the record.** A session that never ends cleanly leaves a record, so **a record counts as open only while its process is alive**, judged by the process id and its start time together so that a reused process id does not keep a dead record alive. Where Hearth cannot establish the start time of a process that exists, it treats the session as open.
* **The hooks cover only sessions that load Hearth's plugin.** Hearth loads it into every session it launches, including those opened with `hearth session`. A session someone starts with plain `claude` is not seen.

### Consequences

* Good, because it needs nothing from the operating system beyond asking whether a process exists and when it started, which both supported systems answer.
* Good, because the same record answers "is this open" for the gateway, for status and for any plugin.
* Bad, because a session started outside Hearth is invisible, and the two-writers failure is possible for it. The operator avoids it by opening agents' sessions with `hearth session`, or by loading the plugin by its path.
* Bad, because a hook that fails to run leaves a session unrecorded. Hooks that fail do not block the session.
* Bad, because the process that runs a hook is taken to be the Claude Code process, which holds for the hooks observed so far (the hook's parent was the Claude Code process, on Claude Code 2.1.327, macOS).

### Confirmation

[Conversation](../primitives/CONVERSATION.md): a live interactive session defers a wake and a closed one lets it run; the gateway's own turns are never counted. The test uses a real process and the real hook command.

## Pros and Cons of the Options

### Inspect the process table

* Good, because it sees every Claude Code process, however it was started.
* Bad, because it needs per-OS code and matching a process to a session by command line or open files, which Claude Code does not promise.

### Ask Claude Code

* Bad, because TODO: no such interface was found in the version checked.

### Plugin hooks

* Good, because Claude Code fires them, including in resumed runs.
* Bad, because only sessions that load the plugin are seen.

## More Information

Written by the builder of the change, with the owner's decisions as the brief. The options are the ones the builder considered, not a recorded discussion. That the hooks fire in `claude -p` runs, fresh and resumed, and that the hook's parent process is Claude Code, was observed with the real program (2.1.327, macOS) before this record was written.
