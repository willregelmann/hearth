"""Where Hearth keeps its state, and the few settings that are Hearth's own rather than an agent's."""
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    claude: Optional[str] = None
    tick_s: float = 1.0
    retry_s: float = 30.0
    retry_max_s: float = 1800.0
    shutdown_grace_s: float = 10.0


_CONFIG_KEYS = {"claude", "tick_s", "retry_s", "retry_max_s", "shutdown_grace_s"}


class Home:
    def __init__(self, root: Path):
        self.root = Path(root).expanduser().absolute()

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Home":
        return cls(Path(env["HEARTH_HOME"]) if env.get("HEARTH_HOME") else Path.home() / ".hearth")

    @property
    def db(self) -> Path:
        return self.root / "hearth.db"

    @property
    def socket(self) -> Path:
        return self.root / "gateway.sock"

    @property
    def lock(self) -> Path:
        return self.root / "gateway.lock"

    @property
    def agents(self) -> Path:
        return self.root / "agents"

    @property
    def sessions(self) -> Path:
        return self.root / "sessions"

    def ensure(self) -> None:
        # The socket and the records of open sessions sit in here; nobody else needs to see them.
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.agents.mkdir(exist_ok=True)
        self.sessions.mkdir(exist_ok=True)

    def config(self, env: Mapping[str, str] = os.environ) -> Config:
        """``config.toml`` in the home, with ``HEARTH_CLAUDE`` overriding where the claude program is."""
        values: dict = {}
        path = self.root / "config.toml"
        if path.exists():
            try:
                values = tomllib.loads(path.read_text())
            except (OSError, tomllib.TOMLDecodeError) as exc:
                raise ConfigError(f"{path}: {exc}") from exc
        unknown = sorted(set(values) - _CONFIG_KEYS)
        if unknown:
            raise ConfigError(f"{path}: unknown setting {', '.join(unknown)}")
        try:
            config = Config(**values)
        except TypeError as exc:
            raise ConfigError(f"{path}: {exc}") from exc
        if env.get("HEARTH_CLAUDE"):
            config = Config(**{**values, "claude": env["HEARTH_CLAUDE"]})
        return config
