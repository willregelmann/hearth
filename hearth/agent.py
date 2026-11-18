"""Agent: a registered Claude Code agent, which is its name and its manifest (docs/primitives/AGENT.md).

The manifest is a TOML file at ``<home>/agents/<name>/agent.toml``. Registering an agent puts it there,
removing one takes it away, and the gateway reads it from there, so the files are the registry.
"""
import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional, Union

from hearth.home import Home

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
MANIFEST = "agent.toml"
DEFAULT_TIMEOUT_S = 1800.0
DEFAULT_CHECK_TIMEOUT_S = 60.0

_TOP_KEYS = {"workdir", "config_dir", "model", "env", "turn_timeout", "claude_args", "plugin", "marketplace", "check"}


class ManifestError(Exception):
    pass


@dataclass(frozen=True)
class Plugin:
    """A directory loaded with ``--plugin-dir``, or an id (``name@marketplace``) installed into the
    agent's configuration directory."""
    dir: Optional[Path] = None
    id: Optional[str] = None

    @property
    def label(self) -> str:
        return self.id if self.id else str(self.dir)


@dataclass(frozen=True)
class Check:
    name: str
    command: Union[str, tuple]
    interval: float
    timeout: float


@dataclass(frozen=True)
class Agent:
    name: str
    manifest: Path
    workdir: Path
    config_dir: Path
    model: Optional[str] = None
    env: Mapping[str, str] = field(default_factory=dict)
    turn_timeout: float = DEFAULT_TIMEOUT_S
    claude_args: tuple = ()
    plugins: tuple = ()
    marketplaces: tuple = ()
    checks: tuple = ()

    def environment(self, home: Home, *, turn: bool, base: Optional[Mapping[str, str]] = None) -> dict:
        """What a program run for this agent sees. ``turn`` marks the gateway's own runs, which the
        plugin's hooks use to tell them from a session a person has open."""
        env = dict(os.environ if base is None else base)
        env.update(self.env)
        env.update(CLAUDE_CONFIG_DIR=str(self.config_dir), HEARTH_HOME=str(home.root), HEARTH_AGENT=self.name,
                   HEARTH_PYTHON=sys.executable)
        env.pop("HEARTH_TURN", None)
        if turn:
            env["HEARTH_TURN"] = "1"
        return env

    def prepare(self) -> None:
        for directory in (self.workdir, self.config_dir):
            if _is_default(directory, self.manifest.parent):
                directory.mkdir(parents=True, exist_ok=True)

    def existing_plugin_dirs(self) -> list:
        return [p.dir for p in self.plugins if p.dir is not None and p.dir.is_dir()]


def _is_default(path: Path, agent_dir: Path) -> bool:
    return path.parent == agent_dir


def agent_dir(home: Home, name: str) -> Path:
    return home.agents / name


def check_name(name: str) -> None:
    if not NAME_RE.match(name):
        raise ManifestError(f"{name!r} is not a usable agent name: use lowercase letters, digits, - and _, "
                            "starting with a letter or digit, at most 64 characters")


def names(home: Home) -> list:
    try:
        entries = sorted(home.agents.iterdir())
    except OSError:
        return []
    return [e.name for e in entries if NAME_RE.match(e.name) and (e / MANIFEST).is_file()]


def exists(home: Home, name: str) -> bool:
    return NAME_RE.match(name) is not None and (agent_dir(home, name) / MANIFEST).is_file()


def load(home: Home, name: str) -> Agent:
    check_name(name)
    path = agent_dir(home, name) / MANIFEST
    try:
        text = path.read_text()
    except OSError as exc:
        raise ManifestError(f"{path}: {exc.strerror or exc}") from exc
    return parse(name, path, text)


def _path(value, base: Path, what: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ManifestError(f"{what} must be a path")
    p = Path(value).expanduser()
    return p if p.is_absolute() else (base / p)


def _number(value, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ManifestError(f"{what} must be a positive number of seconds")
    return float(value)


def parse(name: str, path: Path, text: str) -> Agent:
    """Read a manifest. Anything it can't make sense of is an error, so a typo is never a silent default."""
    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"{path}: {exc}") from exc
    unknown = sorted(set(doc) - _TOP_KEYS)
    if unknown:
        raise ManifestError(f"{path}: unknown setting {', '.join(unknown)}")
    here = path.parent
    workdir = _path(doc["workdir"], here, "workdir") if "workdir" in doc else here / "work"
    config_dir = _path(doc["config_dir"], here, "config_dir") if "config_dir" in doc else here / "claude"
    model = doc.get("model")
    if model is not None and (not isinstance(model, str) or not model):
        raise ManifestError("model must be a string")
    env = doc.get("env", {})
    if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        raise ManifestError("env must be a table of strings")
    claude_args = doc.get("claude_args", [])
    if not isinstance(claude_args, list) or not all(isinstance(a, str) for a in claude_args):
        raise ManifestError("claude_args must be a list of strings")
    timeout = _number(doc["turn_timeout"], "turn_timeout") if "turn_timeout" in doc else DEFAULT_TIMEOUT_S

    plugins = []
    for entry in _tables(doc, "plugin"):
        if set(entry) not in ({"dir"}, {"id"}):
            raise ManifestError("each [[plugin]] needs exactly one of dir or id")
        if "dir" in entry:
            plugins.append(Plugin(dir=_path(entry["dir"], here, "plugin dir")))
        else:
            ident = entry["id"]
            if not isinstance(ident, str) or ident.count("@") != 1 or ident.startswith("@") or ident.endswith("@"):
                raise ManifestError(f"plugin id {ident!r} must look like name@marketplace")
            plugins.append(Plugin(id=ident))

    marketplaces = []
    for entry in _tables(doc, "marketplace"):
        if set(entry) != {"source"} or not isinstance(entry["source"], str) or not entry["source"]:
            raise ManifestError("each [[marketplace]] needs a source and nothing else")
        marketplaces.append(entry["source"])

    checks, seen = [], set()
    for entry in _tables(doc, "check"):
        unknown = sorted(set(entry) - {"name", "command", "interval", "timeout"})
        if unknown:
            raise ManifestError(f"[[check]] has unknown setting {', '.join(unknown)}")
        cname = entry.get("name")
        if not isinstance(cname, str) or not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$", cname):
            raise ManifestError("each [[check]] needs a name of letters, digits, . - and _")
        if cname in seen:
            raise ManifestError(f"two checks are named {cname}")
        seen.add(cname)
        command = entry.get("command")
        if isinstance(command, list) and command and all(isinstance(c, str) and c for c in command):
            command = tuple(command)
        elif not isinstance(command, str) or not command.strip():
            raise ManifestError(f"check {cname} needs a command, a string for the shell or a list of arguments")
        interval = _number(entry["interval"], f"check {cname} interval") if "interval" in entry else None
        if interval is None:
            raise ManifestError(f"check {cname} needs an interval in seconds")
        ctimeout = (_number(entry["timeout"], f"check {cname} timeout") if "timeout" in entry
                    else DEFAULT_CHECK_TIMEOUT_S)
        checks.append(Check(cname, command, interval, ctimeout))

    return Agent(name=name, manifest=path, workdir=workdir, config_dir=config_dir, model=model, env=env,
                 turn_timeout=timeout, claude_args=tuple(claude_args), plugins=tuple(plugins),
                 marketplaces=tuple(marketplaces), checks=tuple(checks))


def _tables(doc: dict, key: str) -> list:
    value = doc.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        raise ManifestError(f"{key} must be written as [[{key}]] tables")
    return value


def render_default(*, workdir: Optional[str], config_dir: Optional[str], model: Optional[str]) -> str:
    lines = []
    if workdir:
        lines.append(f"workdir = {json.dumps(str(workdir))}")
    if config_dir:
        lines.append(f"config_dir = {json.dumps(str(config_dir))}")
    if model:
        lines.append(f"model = {json.dumps(model)}")
    return "\n".join(lines) + ("\n" if lines else "")


def add(home: Home, name: str, text: str) -> Agent:
    """Register an agent from manifest text. It is checked first and written whole, so the gateway
    never reads half a manifest, and an agent that is already registered is left alone."""
    check_name(name)
    directory = agent_dir(home, name)
    path = directory / MANIFEST
    if path.exists():
        raise ManifestError(f"agent {name} is already registered ({path})")
    agent = parse(name, path, text)
    directory.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(MANIFEST + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)
    return agent


def remove(home: Home, name: str) -> None:
    """Unregister an agent. Its directory stays, with the sessions in it, so registering it again
    brings the same conversations back."""
    path = agent_dir(home, name) / MANIFEST
    try:
        path.unlink()
    except FileNotFoundError:
        raise ManifestError(f"agent {name} is not registered") from None


@dataclass
class PluginState:
    declared: str
    loaded: bool
    detail: str = ""


def installed_plugins(claude: str, env: Mapping[str, str]) -> list:
    """What ``claude plugin list`` finds in the configuration directory ``env`` names. Raises
    RuntimeError when it can't say."""
    try:
        done = subprocess.run([claude, "plugin", "list", "--json"], capture_output=True, text=True, env=dict(env),
                              stdin=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"could not run claude plugin list: {getattr(exc, 'strerror', None) or exc}") from exc
    if done.returncode != 0:
        raise RuntimeError(f"claude plugin list exited {done.returncode}")
    try:
        found = json.loads(done.stdout)
    except ValueError:
        raise RuntimeError("claude plugin list printed something that isn't JSON") from None
    if not isinstance(found, list) or not all(isinstance(p, dict) and isinstance(p.get("id"), str) for p in found):
        raise RuntimeError("claude plugin list printed something unexpected")
    return found


def plugin_states(agent: Agent, installed: Optional[list], problem: Optional[str]) -> list:
    """Whether each declared plugin will load, given what is installed (None when that could not be
    found out, with ``problem`` saying why)."""
    states = []
    have = {p["id"] for p in installed or []}
    for plugin in agent.plugins:
        if plugin.dir is not None:
            ok = (plugin.dir / ".claude-plugin" / "plugin.json").is_file()
            states.append(PluginState(plugin.label, ok, "" if ok else f"no .claude-plugin/plugin.json in {plugin.dir}"))
        elif installed is None:
            states.append(PluginState(plugin.label, False, problem or "installed plugins unknown"))
        elif plugin.id in have:
            states.append(PluginState(plugin.label, True))
        else:
            states.append(PluginState(plugin.label, False,
                                      f"not installed in {agent.config_dir}; run: hearth agent install {agent.name}"))
    return states


def plugin_settings(agent: Agent, installed: list) -> str:
    """Settings that make the agent's installed plugins exactly the ones it declares: every other
    installed plugin is switched off, and a declared one that was switched off is switched on."""
    declared = {p.id for p in agent.plugins if p.id}
    return json.dumps({"enabledPlugins": {p["id"]: p["id"] in declared for p in installed}}, sort_keys=True)
