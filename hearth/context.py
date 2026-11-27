"""What the gateway's parts share while it runs."""
import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Callable

from hearth.conversation import Exclusion
from hearth.home import Config, Home

log = logging.getLogger("hearth")


@dataclass
class LiveTurn:
    agent: str
    conversation_id: int
    conversation: str
    source: str
    started: float


@dataclass
class Context:
    home: Home
    conn: sqlite3.Connection
    clock: Callable[[], float]
    config: Config
    claude: str
    poke: Callable[[], None]
    exclusion: Exclusion = field(default_factory=Exclusion)
    live: dict = field(default_factory=dict)
