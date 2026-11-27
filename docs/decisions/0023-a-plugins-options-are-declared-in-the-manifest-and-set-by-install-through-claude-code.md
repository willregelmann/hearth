# A plugin's options are declared in the manifest and set by install through Claude Code

## Context and Problem Statement

A plugin can declare `userConfig` that Claude Code requires before it starts the plugin's MCP server. Front Desk's plugin needs `home` and `python`. A plugin loaded with `--plugin-dir` has nowhere to get them from, so its MCP server never started. The first real turn on Kubernetes showed this: Claude Code logged `Plugin option "home" isn't set`, and the agent truthfully reported that Front Desk's tools weren't there. How does an agent's plugin get its options?

## Considered Options

* The manifest gives each `[[plugin]]` an `options` table, and `hearth agent install` sets them with `claude plugin configure <id> --values-stdin`
* The deployment writes `pluginConfigs` into the configuration directory's `settings.json` itself
* Environment variables

## Decision Outcome

Chosen option: the first. Decided by Claude while getting the real-turn probe to pass (2026-11-27).

* **The manifest is the whole of the agent as Hearth knows it**, so its plugins' options belong there.
* **Claude Code's own command keeps its own settings.** A directory plugin's options are kept under `<name>@inline`, with the name taken from its `plugin.json`.
* **Writing `pluginConfigs` directly was turned down.** That file format is Claude Code's, and it promises nothing about it.
* **Environment variables don't work for this.** A plugin's MCP configuration reads `${user_config.*}` and doesn't read them.

### Consequences

* Good, because a plugin that needs configuration works the same from a manifest on a laptop and in a pod.
* Bad, because options are plain text in the manifest. A secret belongs in the environment, and the option should name a file or a variable, never hold the value.

### Confirmation

[Agent](../primitives/AGENT.md): the manifest holds each plugin's options. [Commands](../interfaces/COMMANDS.md): install sets them and reports each it couldn't set. Test: `test_install_sets_the_options_the_manifest_gives_each_plugin_and_reports_any_it_could_not`.
