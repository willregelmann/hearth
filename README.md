# Hearth

Hearth is a gateway for [Claude Code](https://claude.com/claude-code) agents, and a Claude Code plugin that goes with it.

The gateway is one long-running process. It knows which agents are registered, takes in wakes, and turns each wake into a Claude Code turn in the conversation it was for. The plugin is loaded into every session Hearth launches, and teaches the agent to wait by setting a wake instead of holding a turn open.

A wake is a promise. Hearth writes it down before it says it was accepted, runs it in exactly one conversation, never runs two turns in a conversation at once, never resumes a conversation a person has open, and counts the wake as done only when a turn that was shown it has finished. It survives a restart. Hearth is small on purpose: whatever else an agent needs, such as memory, a way to talk to people or a way to be woken by something, it gets from Claude Code plugins it declares and from sources that send wakes.

The map of what Hearth is, and what must always hold, is in [docs/](docs/INTENT.md).

## Install

Hearth needs Python 3.11 or newer and Claude Code on the machine, and has no Python dependencies.

```
pip install .
```

This puts a `hearth` command on your path. Everything Hearth keeps is under `~/.hearth`, or under the directory `HEARTH_HOME` names. By default it finds `claude` on your path; to point it elsewhere, set `HEARTH_CLAUDE` or put `claude = "/path/to/claude"` in `config.toml` in Hearth's home.

## Run the gateway

```
hearth gateway
```

It runs in the foreground, logs to standard error, and stops cleanly on SIGINT or SIGTERM. Keep it alive however you keep any service alive. Only one gateway runs for a home: a second refuses to start.

## Register an agent

```
hearth agent add ash --workdir ~/work/ash --model sonnet
```

An agent is a name and a manifest, a TOML file at `agents/ash/agent.toml` in Hearth's home. `hearth agent add` writes it, from options or from a file (`--manifest file.toml`, or `-` for standard input). Edit the file, then `hearth agent reload ash`; a manifest that does not parse leaves the agent as it was and says so. `hearth agent remove ash` unregisters it and keeps its directory and its wakes.

Every agent runs as the user the gateway runs as. Agents are told apart by their Claude Code configuration directory, working directory and environment, not by operating system boundaries: one agent can read another's files and credentials. If you need that boundary, put it around Hearth with separate users or containers.

A configuration directory of its own has no login. Sign in once with `hearth session ash` and `/login`, or put credentials in the manifest's `[env]`.

### The manifest

```toml
workdir = "~/work/ash"          # where turns run; default: a directory of its own in Hearth's home
config_dir = "~/.claude"        # Claude Code's configuration directory; default: one of its own in Hearth's home
model = "sonnet"                # optional
turn_timeout = 1800             # seconds before a turn is killed, with everything it started
claude_args = ["--permission-mode", "acceptEdits"]   # extra arguments for every run of claude

[env]                           # extra environment for turns and checks
SOME_TOKEN = "..."

[[marketplace]]                 # added before plugins are installed
source = "some-owner/some-marketplace"

[[plugin]]                      # a plugin installed into the agent's configuration directory
id = "name@marketplace"

[[plugin]]                      # a plugin loaded from a directory
dir = "~/plugins/mine"

[[check]]                       # see "Poll"
name = "inbox"
command = "my-inbox-check"
interval = 60                   # seconds
timeout = 30                    # seconds; default 60
```

An agent's plugins are exactly the ones its manifest declares, plus Hearth's own: any other plugin installed in its configuration directory is switched off for its turns. `hearth agent install ash` adds the marketplaces and installs the declared `id` plugins. A declared plugin that is missing or cannot load is shown in `hearth status` and named in the prompt of each turn; it is never silently absent.

## Wakes

A wake names an agent and a conversation, and carries a source label, a key, and optionally a note and a time before which it must not run. It carries no payload: the source's own plugin shows the agent what it is about.

A conversation is a Claude Code session of one agent. Name it by session id, or by any other string: a name's first turn starts a fresh session, and from then on the name means that session.

Wakes that are due for one conversation are shown together to one turn. If the turn fails, they stay pending and are tried again after a delay that doubles, up to a cap. Wakes that arrive during a turn run in the next one.

### Push

```
hearth wake --agent ash --conversation build-watch --source ci --key run-4411 --note "the build went red"
hearth wake --agent ash --conversation build-watch --in 30m --note "look at the build again"
hearth wake list          # pending and running; --all for the rest
hearth wake cancel 12 --reason 'the deploy was rolled back'
```

The gateway listens on `gateway.sock` in Hearth's home, which only its owner can read or write. The protocol is one JSON request and one JSON response, each ended by a newline, so anything on the machine can push without the `hearth` command:

```
{"op": "wake", "agent": "ash", "conversation": "build-watch", "source": "ci", "key": "run-4411", "note": "the build went red"}
{"ok": true, "id": 12, "duplicate": false, "state": "pending", "conversation": "build-watch", "not_before": null}
```

`delay` (seconds) or `not_before` (epoch seconds) hold a wake back. A key the gateway has already accepted from that source for that agent is acknowledged with `"duplicate": true` and raises nothing, however long ago, so a source can retry safely. A request that can't be honoured gets `{"ok": false, "error": "..."}`. The other operations are `wake.list`, `wake.cancel`, `agent.reload`, `agent.list` and `status`.

### Poll

A source that doesn't push is polled. A check is a command and an interval in the manifest; Hearth runs it in the agent's working directory with the agent's environment, nothing on standard input, and a timeout. A check prints zero or more lines, each a JSON object naming a conversation and a key, with an optional note:

```
{"conversation": "inbox", "key": "mail-1031", "note": "Ada wrote about the invoice"}
```

Each line is a wake whose source is the check's name. Checks are edge-triggered: a key raises a wake when it appears and was absent from the check's previous output, and never while a wake with that key is still pending or running. What a check last printed is kept, so a restart raises nothing again. A check that exits non-zero, times out or prints a line it can't read raises nothing and is shown as failed in `hearth status`; it is never taken for "nothing to do". The previous keys are kept, so a check that recovers does not raise everything again.

## The plugin

The plugin ships inside the package and is passed to every session Hearth launches, so it needs no install step. `hearth plugin-dir` prints where it is, for loading into a session you start yourself with `claude --plugin-dir`.

- When a session starts, a hook records it as open (unless it is a turn the gateway is running) and tells the agent that Hearth exists, its agent name, this conversation's id, and how to wait: set a wake for this conversation and end the turn. When the session ends, the hook clears the record. A record counts only while its process is alive.
- `/hearth:wake` sets a wake for this conversation, `/hearth:status` shows status, and `/hearth:agents` lists the agents. Each runs the `hearth` command.

Hearth defers a wake for a conversation that a live session has open, and runs it once the session closes. It knows about sessions that load the plugin, which is every session Hearth launches, including `hearth session ash`, which opens an interactive Claude Code session as the agent with the configuration directory, environment and plugins its turns use. `hearth agent install` also writes Hearth's session hooks into the agent's configuration directory, so a session started there with plain `claude` is seen too; a configuration directory that hasn't been installed since this release isn't.

## Status

```
hearth status          # for a person
hearth status --json   # for a script
```

When the gateway started; per agent, its declared plugins and whether each loaded, its checks with when each last ran and how it last failed, its live turns, its open sessions, its pending wakes with when each is tried next and why it is waiting, and its recent turns. Turns are recorded as agent, conversation, session, what woke them, when they started and ended, and how they ended. Prompt and reply text are never written down.

## What Hearth deliberately does not do

- It does not keep memory, an agent's account of itself, or a list of what an agent owes. Declare a plugin that does.
- It does not talk to people or to other agents. Declare a plugin that does, and have its source push or be polled.
- It does not deliver an agent's reply anywhere. A woken turn is told that its reply text goes to no one.
- It does not isolate agents from each other beyond giving each its own configuration directory.
- It does not provision users, need root, or manage the service it runs as.
- It does not know of any particular source of wakes. There is no adapter and no listener for a source: it pushes, or it is polled.
- It does not see a session that was started without the plugin.
- It has no web interface. `hearth status --json` is what one would read.

## Development

```
uv run --extra dev pytest
```

The tests fake only the `claude` program and the clock. Everything else is the real gateway, its real socket and its real command.
