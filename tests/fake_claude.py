"""A stand-in for the claude program, at the boundary Hearth meets it.

It does what Claude Code does that Hearth depends on: takes the options Hearth passes, keeps sessions
by id, runs the SessionStart and SessionEnd hooks of the plugin directories it is given (the behaviour
observed with the real program), prints a JSON result, and answers the ``plugin`` subcommands.

What it does is steered from the directory named by FAKE_CLAUDE_DIR:
  mode           JSON: {"fail": "exit"|"garbage", "sleep": seconds, "child": true}
  hold           while this file exists, a run waits
  log.jsonl      one line for each run starting and ending
  sessions/      one file per session it knows
"""
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

CTRL = Path(os.environ["FAKE_CLAUDE_DIR"])
VALUE_OPTIONS = {"--output-format", "--model", "--resume", "--settings", "--plugin-dir", "--permission-mode"}
REPLY = "SECRET-REPLY-TEXT"


def log(entry: dict) -> None:
    with open(CTRL / "log.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")


def plugin_command(args: list) -> int:
    config = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(CTRL / "config")))
    store = config / "fake_plugins.json"
    if args[:1] == ["list"]:
        print(store.read_text() if store.exists() else "[]")
        return 0
    if args[:2] == ["marketplace", "add"]:
        with open(CTRL / "marketplaces.jsonl", "a") as f:
            f.write(json.dumps({"source": args[2], "config": str(config)}) + "\n")
        print(json.dumps({"command": "marketplace-add", "outcome": "ok", "message": f"added {args[2]}"}))
        return 0
    if args[:1] == ["configure"] and "--values-stdin" in args:
        refused = (CTRL / "unconfigurable").read_text().split() if (CTRL / "unconfigurable").exists() else []
        if args[1] in refused:
            print(f"No installed plugin has the id \"{args[1]}\".", file=sys.stderr)
            return 1
        config.mkdir(parents=True, exist_ok=True)
        path = config / "settings.json"
        settings = json.loads(path.read_text()) if path.exists() else {}
        settings.setdefault("pluginConfigs", {}).setdefault(args[1], {}).setdefault("options", {}).update(
            json.loads(sys.stdin.read()))
        path.write_text(json.dumps(settings))
        print("Configuration saved. Restart Claude Code to apply it.")
        return 0
    if args[:1] == ["install"]:
        refused = (CTRL / "unknown-plugins").read_text().split() if (CTRL / "unknown-plugins").exists() else []
        if args[1] in refused:
            print(json.dumps({"command": "install", "outcome": "failed", "message": f"{args[1]} is not in any marketplace"}))
            return 1
        config.mkdir(parents=True, exist_ok=True)
        have = json.loads(store.read_text()) if store.exists() else []
        have.append({"id": args[1], "enabled": True})
        store.write_text(json.dumps(have))
        print(json.dumps({"command": "install", "outcome": "ok", "message": f"installed {args[1]}"}))
        return 0
    return 2


def _hook_sources(plugin_dirs: list) -> list:
    """Where hooks come from, as Claude Code reads them: the settings file in the configuration
    directory, then each plugin directory's hooks file."""
    sources = []
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    if config and (Path(config) / "settings.json").exists():
        sources.append((None, json.loads((Path(config) / "settings.json").read_text()).get("hooks", {})))
    for directory in plugin_dirs:
        hooks_file = Path(directory) / "hooks" / "hooks.json"
        if hooks_file.exists():
            sources.append((directory, json.loads(hooks_file.read_text())["hooks"]))
    return sources


def run_hooks(event: str, plugin_dirs: list, session: str, source: str) -> list:
    contexts = []
    for directory, hooks in _hook_sources(plugin_dirs):
        for group in hooks.get(event, []):
            for hook in group["hooks"]:
                env = dict(os.environ, CLAUDE_PID=str(os.getpid()))
                if directory is not None:
                    env["CLAUDE_PLUGIN_ROOT"] = str(directory)
                payload = {"session_id": session, "cwd": os.getcwd(), "hook_event_name": event, "source": source}
                done = subprocess.run(hook["command"], shell=True, input=json.dumps(payload), env=env,
                                      capture_output=True, text=True)
                try:
                    out = json.loads(done.stdout)
                    contexts.append(out["hookSpecificOutput"]["additionalContext"])
                except (ValueError, KeyError):
                    pass
    return contexts


def result(session: str, *, error: bool = False, subtype: str = "success") -> str:
    return json.dumps({"type": "result", "subtype": subtype, "is_error": error, "result": REPLY,
                       "session_id": session, "num_turns": 1})


def main(argv: list) -> int:
    while argv[:1] == ["--plugin-dir"]:      # options before the subcommand, as Claude Code takes them
        argv = argv[2:]
    if argv[:1] == ["plugin"]:
        return plugin_command(argv[1:])
    options: dict = {"--plugin-dir": []}
    i = 0
    while i < len(argv) - 1:
        a = argv[i]
        if a in VALUE_OPTIONS:
            if a == "--plugin-dir":
                options[a].append(argv[i + 1])
            else:
                options[a] = argv[i + 1]
            i += 2
        else:
            i += 1
    prompt = argv[-1]
    mode = json.loads((CTRL / "mode").read_text()) if (CTRL / "mode").exists() else {}
    resume = options.get("--resume")
    sessions = CTRL / "sessions"
    sessions.mkdir(exist_ok=True)
    if resume and not (sessions / resume).exists():
        print(json.dumps({"type": "result", "subtype": "error", "is_error": True, "result": REPLY,
                          "session_id": resume}))
        return 1
    session = resume or str(uuid.uuid4())
    (sessions / session).touch()
    contexts = run_hooks("SessionStart", options["--plugin-dir"], session, "resume" if resume else "startup")
    log({"event": "start", "pid": os.getpid(), "t": time.time(), "resume": resume, "session": session,
         "cwd": os.getcwd(), "model": options.get("--model"), "settings": options.get("--settings"),
         "config_dir": os.environ.get("CLAUDE_CONFIG_DIR"), "plugin_dirs": options["--plugin-dir"],
         "prompt": prompt, "agent": os.environ.get("HEARTH_AGENT"), "turn": os.environ.get("HEARTH_TURN"),
         "foo": os.environ.get("FOO"), "contexts": contexts, "argv": argv})
    if mode.get("child"):
        child = subprocess.Popen(["sleep", "60"])
        (CTRL / "child.pid").write_text(str(child.pid))
    waited = 0.0
    while (CTRL / "hold").exists() and waited < 60:
        time.sleep(0.02)
        waited += 0.02
    time.sleep(mode.get("sleep", 0))
    with open(sessions / session, "a") as f:
        f.write(prompt + "\n")
    run_hooks("SessionEnd", options["--plugin-dir"], session, "other")
    log({"event": "end", "pid": os.getpid(), "t": time.time(), "session": session})
    if mode.get("fail") == "exit":
        print(result(session, error=True, subtype="error_during_execution"))
        return 1
    if mode.get("fail") == "garbage":
        print("this is not a result")
        return 0
    print(result(session))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
