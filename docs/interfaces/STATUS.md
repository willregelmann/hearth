# Status

What the gateway reports about itself and its [agents](../primitives/AGENT.md), to an operator or a script, over the same socket as [push](PUSH.md). Status is read-only.

## What passes

| Report | What it shows |
|---|---|
| Started | When the gateway started |
| Plugins | Per agent, each declared plugin and whether it loaded, with the reason when it did not |
| Checks | Per agent, each [check](CHECKS.md) with when it last ran and its last failure, if any |
| Live turns | Per agent, which turns are running and in which conversation |
| Open sessions | Per agent, the sessions a person has open |
| Wakes | Per agent, the pending [wakes](../primitives/WAKE.md), including those that failed and those deferred, with when each is tried next |
| Recent turns | Per agent, what started each recent turn and how it ended, without what was said in it |

## Invariants

- **Status reports. It never starts a turn, raises a wake, or changes anything.**
- **Whatever Hearth is holding back, it says why: a conversation that is deferred, a wake that failed, a plugin that did not load, a check that failed.**
- Status never shows prompt text or reply text, and never a check's raw output.
- An agent whose manifest could not be read is listed with the reason, never left out.
- Nothing the gateway does waits on a reader of status.
