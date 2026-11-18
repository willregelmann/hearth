# Commands

The `hearth` command: what the operator, and the agents themselves, run to run the gateway and to work with agents and wakes. On the other side is a person at a terminal, a script, or an agent using its shell.

## What passes

| Command | What it does |
|---|---|
| Gateway | Runs the gateway in the foreground |
| Add, remove, list, reload | Registers an agent from a manifest, unregisters it, lists the registered agents, or re-reads a manifest |
| Install | Installs an agent's declared plugins into its configuration directory, adding the marketplaces its manifest names first |
| Session | Opens an interactive Claude Code session as an agent, with the configuration directory, environment and plugins its turns use |
| Wake | Raises a wake, lists wakes, or cancels a pending one |
| Status | Shows [status](STATUS.md) for a person, or as JSON on request |

## Invariants

- **An interactive session opened as an agent runs exactly as that agent's turns do: same configuration directory, working directory, environment and plugins.**
- Registering, removing and reloading work whether or not the gateway is running, and when it is running they take effect without a restart.
- A command that can't complete says so and exits non-zero. It never reports success for something it did not do.
- Install reports each declared plugin it could not install, and changes no plugin the manifest does not declare.
- A wake raised with no conversation named goes to the conversation the caller is in, when it is in one, and is refused otherwise.
- No command needs more privilege than the gateway's own user.
