"""The ``hearth`` command (docs/interfaces/COMMANDS.md)."""
import argparse
import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime
from typing import Optional

from hearth import agent as agents
from hearth import claude, client, conversation, gateway, hook
from hearth.db import connect
from hearth.home import ConfigError, Home

EX_UNAVAILABLE = 3


class CommandError(Exception):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


_DELAY = re.compile(r"(\d+(?:\.\d+)?)([smhd])")
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_delay(text: str) -> float:
    """``90s``, ``30m``, ``2h``, ``1d``, or a run of them such as ``1h30m``."""
    rest, total = text.strip().lower(), 0.0
    if not rest:
        raise CommandError("a delay is a number with a unit: 90s, 30m, 2h, 1d, or 1h30m")
    while rest:
        m = _DELAY.match(rest)
        if not m:
            raise CommandError(f"cannot read {text!r} as a delay: use 90s, 30m, 2h, 1d, or 1h30m")
        total += float(m.group(1)) * _UNITS[m.group(2)]
        rest = rest[m.end():]
    return total


def parse_time(text: str) -> float:
    """An ISO 8601 time (local time when it names no zone), or seconds since the epoch."""
    try:
        return float(text)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        raise CommandError(f"cannot read {text!r} as a time: use ISO 8601, such as 2026-01-31T09:00:00Z") from None


def _ask(home: Home, payload: dict) -> dict:
    """A request to the gateway, whose refusal is an error."""
    try:
        response = client.request(home, payload)
    except client.GatewayUnavailable as exc:
        raise CommandError(str(exc), EX_UNAVAILABLE) from exc
    if not response.get("ok"):
        raise CommandError(response.get("error", "the gateway refused the request"))
    return response


def _notify(home: Home, agent: Optional[str]) -> str:
    """Tell a running gateway an agent changed. Returns a line about what happened."""
    try:
        response = client.request(home, {"op": "agent.reload", **({"agent": agent} if agent else {})})
    except client.GatewayUnavailable:
        return "the gateway is not running; it reads manifests when it starts"
    if not response.get("ok"):
        return f"the gateway could not apply it: {response.get('error')}"
    return "the gateway has applied it"


def _stamp(t: Optional[float]) -> str:
    return "-" if t is None else time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime(t))


def _ago(now: float, t: Optional[float]) -> str:
    if t is None:
        return "never"
    s = max(0, int(now - t))
    return f"{s}s ago" if s < 120 else f"{s // 60}m ago" if s < 7200 else f"{s // 3600}h ago"


# Commands ------------------------------------------------------------------------------------------

def cmd_gateway(args, home: Home) -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        home.config()
        asyncio.run(gateway.serve(home))
    except (gateway.GatewayError, ConfigError) as exc:
        raise CommandError(str(exc)) from exc
    return 0


def cmd_agent_add(args, home: Home) -> int:
    if args.manifest:
        text = sys.stdin.read() if args.manifest == "-" else open(args.manifest).read()
    else:
        text = agents.render_default(workdir=args.workdir, config_dir=args.config_dir, model=args.model)
    agent = agents.add(home, args.name, text)
    print(f"registered {agent.name} ({agent.manifest})")
    print(_notify(home, agent.name))
    return 0


def cmd_agent_remove(args, home: Home) -> int:
    agents.remove(home, args.name)
    print(f"removed {args.name}; its directory and sessions are kept, and so are its wakes")
    print(_notify(home, args.name))
    return 0


def cmd_agent_list(args, home: Home) -> int:
    rows = []
    for name in agents.names(home):
        try:
            agent = agents.load(home, name)
            rows.append({"name": name, "manifest": str(agent.manifest), "error": None})
        except agents.ManifestError as exc:
            rows.append({"name": name, "manifest": str(agents.agent_dir(home, name) / agents.MANIFEST),
                         "error": str(exc)})
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    if not rows:
        print("no agents are registered")
    for r in rows:
        print(f"{r['name']}  {r['manifest']}" + (f"  INVALID: {r['error']}" if r["error"] else ""))
    return 0


def cmd_agent_reload(args, home: Home) -> int:
    for name in [args.name] if args.name else agents.names(home):
        agents.load(home, name)
    print(_notify(home, args.name))
    return 0


def cmd_agent_install(args, home: Home) -> int:
    agent = agents.load(home, args.name)
    claude_path = claude.program(home.config().claude)
    env = agent.environment(home, turn=False)
    agent.prepare()
    failed = 0

    def run(*argv: str) -> str:
        done = subprocess.run([claude_path, "plugin", *argv, "--json"], capture_output=True, text=True, env=env,
                              stdin=subprocess.DEVNULL, timeout=600)
        message = ""
        for line in reversed(done.stdout.splitlines()):
            try:
                message = json.loads(line).get("message", "")
                break
            except (ValueError, AttributeError):
                continue
        if done.returncode != 0:
            raise CommandError(message or f"claude plugin {argv[0]} exited {done.returncode}")
        return message

    for source in agent.marketplaces:
        try:
            print(f"marketplace {source}: {run('marketplace', 'add', source) or 'ok'}")
        except (CommandError, OSError, subprocess.SubprocessError) as exc:
            failed += 1
            print(f"marketplace {source}: FAILED: {exc}")
    for plugin in agent.plugins:
        if plugin.id:
            try:
                print(f"plugin {plugin.id}: {run('install', plugin.id) or 'ok'}")
            except (CommandError, OSError, subprocess.SubprocessError) as exc:
                failed += 1
                print(f"plugin {plugin.id}: FAILED: {exc}")
        elif (plugin.dir / ".claude-plugin" / "plugin.json").is_file():
            print(f"plugin {plugin.dir}: a directory, loaded as it is")
        else:
            failed += 1
            print(f"plugin {plugin.dir}: FAILED: no .claude-plugin/plugin.json there")
    print(_notify(home, agent.name))
    return 1 if failed else 0


def cmd_session(args, home: Home) -> int:
    agent = agents.load(home, args.agent)
    claude_path = claude.program(home.config().claude)
    env = agent.environment(home, turn=False)
    try:
        installed = agents.installed_plugins(claude_path, env)
    except RuntimeError as exc:
        raise CommandError(str(exc)) from exc
    argv = [claude_path, *claude.launch_args(agent, agents.plugin_settings(agent, installed))]
    if args.resume:
        home.ensure()
        session = conversation.lookup(connect(home.db), agent.name, args.resume)
        if session is None:
            raise CommandError(f"{args.resume!r} is not a session of {agent.name} and names none yet")
        argv += ["--resume", session]
    rest = args.claude_args[1:] if args.claude_args[:1] == ["--"] else args.claude_args
    argv += rest
    agent.prepare()
    try:
        os.chdir(agent.workdir)
        os.execvpe(claude_path, argv, env)
    except OSError as exc:
        raise CommandError(f"could not start {claude_path}: {exc.strerror or exc}") from exc
    return 0


def cmd_wake(args, home: Home) -> int:
    if args.action == "list":
        return _wake_list(args, home)
    if args.action == "cancel":
        if args.id is None:
            raise CommandError("say which wake to cancel: hearth wake cancel ID")
        response = _ask(home, {"op": "wake.cancel", "id": args.id})
        print(f"cancelled wake {response['id']}")
        return 0
    agent = args.agent or os.environ.get("HEARTH_AGENT")
    if not agent:
        raise CommandError("which agent? give --agent, or run this inside one of Hearth's sessions")
    ref = args.conversation or os.environ.get("HEARTH_CONVERSATION") or os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not ref:
        raise CommandError("which conversation? give --conversation (a session id or a name)")
    payload = {"op": "wake", "agent": agent, "conversation": ref, "source": args.source,
               "key": args.key or str(uuid.uuid4())}
    if args.note:
        payload["note"] = args.note
    if args.delay and args.at:
        raise CommandError("give --in or --at, not both")
    if args.delay:
        payload["delay"] = parse_delay(args.delay)
    if args.at:
        payload["not_before"] = parse_time(args.at)
    response = _ask(home, payload)
    when = f", not before {_stamp(response['not_before'])}" if response.get("not_before") else ""
    if response["duplicate"]:
        print(f"already accepted as wake {response['id']} ({response['state']}); nothing new was raised")
    else:
        print(f"accepted wake {response['id']} for {agent} in {response['conversation']}{when}")
    return 0


def _wake_list(args, home: Home) -> int:
    payload: dict = {"op": "wake.list"}
    if args.agent:
        payload["agent"] = args.agent
    if args.all:
        payload["states"] = "all"
    wakes = _ask(home, payload)["wakes"]
    if args.json:
        print(json.dumps(wakes, indent=2))
        return 0
    if not wakes:
        print("no wakes")
    for w in wakes:
        line = f"{w['id']:>5}  {w['state']:<8} {w['agent']}/{w['conversation']}  {w['source']}  {w['key']}"
        if w["note"]:
            line += f"  {w['note']!r}"
        if w["state"] == "pending":
            line += f"  next try {_stamp(w['next_try'])}" if w["next_try"] else "  due now"
            if w["deferred"]:
                line += "  (open in a live session: deferred)"
            if w["failures"]:
                line += f"  (failed {w['failures']}x: {w['last_failure']})"
        print(line)
    return 0


def cmd_status(args, home: Home) -> int:
    status = _ask(home, {"op": "status"})
    if args.json:
        print(json.dumps(status, indent=2))
        return 0
    now = status["now"]
    print(f"gateway pid {status['pid']}, started {_stamp(status['started'])} ({_ago(now, status['started'])})")
    if not status["agents"]:
        print("no agents are registered")
    for a in status["agents"]:
        print(f"\nagent {a['name']}" + (f"  {a['manifest']}" if a.get("manifest") else ""))
        if a.get("error"):
            print(f"  manifest problem: {a['error']}")
        for p in a.get("plugins", []):
            print(f"  plugin {p['declared']}: " + ("loaded" if p["loaded"] else f"NOT LOADED: {p['detail']}"))
        for c in a.get("checks", []):
            state = ("never run" if c["last_run"] is None else
                     "ok" if c["last_ok"] else f"FAILED {_ago(now, c['last_error_at'])}: {c['last_error']}")
            print(f"  check {c['name']} every {c['interval']:g}s, last run {_ago(now, c['last_run'])}: {state}")
        for t in a.get("live_turns", []):
            print(f"  turn running in {t['conversation']} since {_ago(now, t['started'])} ({t['source']})")
        for s in a.get("open_sessions", []):
            print(f"  session open: {s['session']} (pid {s['pid']})")
        for w in a.get("wakes", []):
            extra = (" deferred: open in a live session" if w["deferred"] else
                     f" next try {_stamp(w['next_try'])}" if w["next_try"] else "")
            if w["failures"]:
                extra += f" failed {w['failures']}x: {w['last_failure']}"
            print(f"  wake {w['id']} {w['state']} {w['conversation']} from {w['source']}{extra}")
        for t in a.get("recent_turns", []):
            detail = f": {t['detail']}" if t["detail"] else ""
            print(f"  turn {t['id']} {t['outcome']} in {t['conversation']} from {t['source']}, "
                  f"{_ago(now, t['started'])}{detail}")
    return 0


def cmd_plugin_dir(args, home: Home) -> int:
    print(claude.PLUGIN_DIR)
    return 0


def cmd_hook(args, home: Home) -> int:
    return hook.run(args.event, sys.stdin.read())


# Parser --------------------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hearth", description="A gateway that turns wakes into Claude Code turns.")
    sub = p.add_subparsers(dest="command", required=True, metavar="command")

    sub.add_parser("gateway", help="run the gateway in the foreground").set_defaults(fn=cmd_gateway)

    agent_p = sub.add_parser("agent", help="register and manage agents")
    asub = agent_p.add_subparsers(dest="agent_command", required=True, metavar="action")
    add = asub.add_parser("add", help="register an agent")
    add.add_argument("name")
    add.add_argument("--manifest", help="a manifest file to register, or - for standard input")
    add.add_argument("--workdir")
    add.add_argument("--config-dir")
    add.add_argument("--model")
    add.set_defaults(fn=cmd_agent_add)
    rm = asub.add_parser("remove", help="unregister an agent")
    rm.add_argument("name")
    rm.set_defaults(fn=cmd_agent_remove)
    ls = asub.add_parser("list", help="list the registered agents")
    ls.add_argument("--json", action="store_true")
    ls.set_defaults(fn=cmd_agent_list)
    rl = asub.add_parser("reload", help="re-read a manifest, or every manifest")
    rl.add_argument("name", nargs="?")
    rl.set_defaults(fn=cmd_agent_reload)
    ins = asub.add_parser("install", help="install an agent's declared plugins")
    ins.add_argument("name")
    ins.set_defaults(fn=cmd_agent_install)

    ses = sub.add_parser("session", help="open an interactive Claude Code session as an agent")
    ses.add_argument("agent")
    ses.add_argument("--resume", metavar="SESSION_OR_NAME", help="resume a conversation of the agent")
    ses.add_argument("claude_args", nargs=argparse.REMAINDER, help="more arguments for claude, after --")
    ses.set_defaults(fn=cmd_session)

    wk = sub.add_parser("wake", help="raise a wake, or: wake list, wake cancel ID")
    wk.add_argument("action", nargs="?", choices=["list", "cancel"])
    wk.add_argument("id", nargs="?", type=int)
    wk.add_argument("--agent", help="default: $HEARTH_AGENT")
    wk.add_argument("--conversation", help="a session id or a name; default: the conversation you are in")
    wk.add_argument("--source", default="cli", help="the label the wake carries")
    wk.add_argument("--key", help="what makes this wake the same wake if it is raised again")
    wk.add_argument("--note")
    wk.add_argument("--in", dest="delay", metavar="DELAY", help="not before this long from now, such as 30m")
    wk.add_argument("--at", metavar="TIME", help="not before this time (ISO 8601)")
    wk.add_argument("--all", action="store_true", help="with list: include finished and cancelled wakes")
    wk.add_argument("--json", action="store_true", help="with list: JSON")
    wk.set_defaults(fn=cmd_wake)

    st = sub.add_parser("status", help="show what the gateway is doing")
    st.add_argument("--json", action="store_true")
    st.set_defaults(fn=cmd_status)

    sub.add_parser("plugin-dir", help="print where Hearth's Claude Code plugin is").set_defaults(fn=cmd_plugin_dir)

    hk = sub.add_parser("hook", help="run by the plugin's hooks")
    hk.add_argument("event", choices=["session-start", "session-end"])
    hk.set_defaults(fn=cmd_hook)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args, Home.from_env())
    except CommandError as exc:
        print(f"hearth: {exc}", file=sys.stderr)
        return exc.code
    except (agents.ManifestError, conversation.ConversationError, ConfigError) as exc:
        print(f"hearth: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"hearth: {exc.strerror or exc}", file=sys.stderr)
        return 1
