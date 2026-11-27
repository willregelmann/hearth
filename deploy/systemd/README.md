# Running each agent as its own Linux user

One agent is one Linux user with one gateway: a `hearth@<agent>` systemd unit running `hearth gateway` as that user, whose home holds the agent's whole state (`~/.hearth`: the wake queue, conversations, open-session records and, by default, the Claude Code configuration directory and working directory). It is the same shape as the Kubernetes deployment, with the user in place of the namespace and the home in place of the volume. Hearth needs no change for it.

## Setting up an agent (as root, once)

```
# Hearth, shared and read-only to the agents
python3 -m venv /opt/hearth && /opt/hearth/bin/pip install 'hearth[otel] @ git+https://github.com/willregelmann/hearth'
install -m 644 deploy/systemd/hearth@.service /etc/systemd/system/

# The agent's user, its home readable by nobody else
useradd --create-home --shell /bin/bash wren && chmod 700 /home/wren

# As the agent: Claude Code, its manifest, its settings
sudo -iu wren sh -c 'curl -fsSL https://claude.ai/install.sh | bash'
sudo -iu wren /opt/hearth/bin/hearth agent add wren --manifest - < wren.toml
sudo -iu wren sh -c 'mkdir -p ~/.config/hearth && umask 077 && cat > ~/.config/hearth/env' < wren.env
sudo -iu wren /opt/hearth/bin/hearth agent install wren

systemctl enable --now hearth@wren
```

`wren.env` holds what the gateway's environment needs, such as `CLAUDE_CODE_OAUTH_TOKEN=...` (from `claude setup-token`) and the `OTEL_*` variables. It is never committed.

## Working with an agent

Everything runs as the agent:

```
sudo -iu wren /opt/hearth/bin/hearth status
sudo -iu wren /opt/hearth/bin/hearth wake --conversation house --note "check the boiler"
sudo -iu wren /opt/hearth/bin/hearth session wren        # an interactive session the gateway sees as open
systemctl restart hearth@wren                            # touches no other agent
journalctl -u hearth@wren
```

## What the boundary is, and isn't

- **Between agents it is the OS:** one agent's turns can't read another's home, transcripts or credentials, and can't push to its gateway, whose socket only its own user can open. A source that runs as another user raises wakes by being polled, or runs as the agent.
- **It is soft while the agents' users can sudo.** That is a choice about the host, not about Hearth. To make it hard, give the agents no sudo, or add `NoNewPrivileges=yes` in a drop-in (`systemctl edit hearth@wren`), which also stops sudo from inside a turn.
- **Turns are permissive by default** (they never stop to ask), so a turn can do anything its user can. The user is the boundary.

## Checked by

`deploy/systemd/test/run.sh`, in a container with real users: each agent's turns run as its own user; another agent can't read its state or push to it; restarting one agent's gateway leaves another's running turn alone; and systemd accepts the unit.
