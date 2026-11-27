# Agent

A registered Claude Code agent: a name and a manifest. The manifest is the whole of the agent as Hearth knows it: where its turns work, which Claude Code configuration directory they use, an optional model, extra environment, how long a turn may take, the plugins it loads with the options each needs, and the [checks](../interfaces/CHECKS.md) that poll for it. Everything else the agent is lives in Claude Code, in that configuration directory and working directory.

All agents run as the gateway's own OS user. What keeps them apart is configuration, not custody: each has its own configuration directory unless its manifest points somewhere else, and nothing stops one from reading another's files or credentials.

## Invariants

- **An agent's plugins are exactly the ones its manifest declares, plus Hearth's own.** A turn loads nothing else, including plugins that happen to be installed in its configuration directory.
- **A declared plugin that could not be installed or loaded is reported on [status](../interfaces/STATUS.md), never silently missing.**
- **Adding, removing or reloading one agent never disturbs another agent's turns or wakes.**
- A reload that can't be applied, such as a manifest that doesn't parse, leaves the agent as it was and says so.
- Removing an agent starts no new turn for it. A turn already running finishes, and the agent's wakes are kept, not discarded.
- An agent's configuration directory is its own unless the manifest says otherwise.
- A wake, a conversation name and a session belong to exactly one agent. The same name in two agents is two conversations.
