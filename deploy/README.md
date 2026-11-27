# Running Hearth on Kubernetes

One agent is one namespace with one gateway. The gateway is a StatefulSet with exactly one replica,
whose volume is the agent's whole home: Hearth's state (the wake queue, conversations, open-session
records), the Claude Code configuration directory and its transcripts, and the working directory.
The volume is mounted by that pod alone, so Hearth's single-gateway lock and its SQLite file hold
exactly as they do on a laptop.

```
deploy/gateway/Containerfile   Hearth, a pinned Claude Code, tini; runs hearth-start
deploy/gateway/hearth-start    puts the manifest in place, installs, then execs `hearth gateway`
deploy/k8s/agent/              the kustomize base for one agent
deploy/test/                   the end-to-end run on kind, with the test suite's stand-in for Claude Code
```

Nothing here names a plugin. An agent's plugins, its checks and its other services (a memory
server, a message desk) belong to the deployment that composes them: an image built `FROM` the
gateway image adds plugin directories, and an overlay of `deploy/k8s/agent` adds the manifest and
whatever else runs in the agent's namespace.

## An agent's overlay

```yaml
# kustomization.yaml
namespace: agent-ash
resources: [namespace.yaml, <path to>/deploy/k8s/agent]
images:
  - {name: hearth-gateway, newName: registry.example/hearth-gateway, newTag: "<tag>"}
configMapGenerator:
  - name: hearth-agent
    literals: [name=ash]
    files: [agent.toml, config.toml]
secretGenerator:      # or create hearth-secrets by hand; its keys become the gateway's environment
  - name: hearth-secrets
    envs: [secrets.env]   # e.g. CLAUDE_CODE_OAUTH_TOKEN=... (never committed)
```

`agent.toml` is an ordinary Hearth manifest. Leave `workdir` and `config_dir` out, or keep them
under `/home/agent`, so both live on the volume; Hearth creates its defaults, but not a directory a
manifest names. Plain `claude` in the pod uses `CLAUDE_CONFIG_DIR` (`/home/agent/claude`), so set
`config_dir` to that when people will start sessions there by hand. `config.toml` is Hearth's own settings.
Keep `shutdown_grace_s` below the pod's `terminationGracePeriodSeconds` (60), so a running turn can
finish before the kubelet kills it.

## Working with an agent

Everything the `hearth` command does is run in the pod, as the gateway's user:

```
kubectl -n agent-ash exec hearth-0 -- hearth status
kubectl -n agent-ash exec hearth-0 -- hearth wake --conversation build --note "look at the build"
kubectl -n agent-ash exec -it hearth-0 -- hearth session ash     # an interactive session as the agent
```

An interactive session belongs in the pod, so the gateway can see it is open and defers wakes for
its conversation. `hearth agent install`, which `hearth-start` runs on every start, writes Hearth's
record-only session hooks into the configuration directory, so even a plain `claude` started there
is seen.

## Requirements and limits

- **Block storage, one node (ReadWriteOnce).** Never NFS or another shared filesystem: Hearth's
  lock is advisory and node-local there, and SQLite's write-ahead log is unsafe on it.
- **Never scale the StatefulSet.** A second gateway on the same home refuses to start, but a
  second replica would get a second volume, which is a second, empty agent.
- **The model's credentials** come from the `hearth-secrets` Secret as environment variables, which
  every turn inherits.
- **NetworkPolicy** keeps other namespaces out of the agent's. kind's default network doesn't
  enforce NetworkPolicy, so the end-to-end run doesn't test it.

## The end-to-end run

```
deploy/test/kind-e2e.sh          # build, deploy to a fresh kind cluster, check, delete the cluster
deploy/test/kind-e2e.sh --keep   # leave the cluster for a look
```

It checks, in a real pod:
- a wake reaches the conversation it names;
- a wake survives the pod being force-killed mid-turn, and the next turn is told it may have been shown before;
- a not-before wake never fires early across a reschedule;
- a second gateway on the same home refuses to start;
- the record-only session hooks are installed.
