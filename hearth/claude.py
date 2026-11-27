"""What Hearth asks of Claude Code, and what it makes of the answer (docs/interfaces/CLAUDE-CODE.md)."""
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import hearth
from hearth.agent import Agent

PLUGIN_DIR = Path(hearth.__file__).parent / "plugin"


def program(configured: Optional[str]) -> str:
    """Where the claude program is: configured, else on the PATH. A name that isn't found is returned
    as it is, and running it fails visibly."""
    return configured or shutil.which("claude") or "claude"


def launch_args(agent: Agent, settings: str) -> list:
    """The options every run for an agent shares, a turn or a session a person opens. The manifest's own
    arguments come first: one of them may take any number of values, and must not reach the prompt."""
    args = list(agent.claude_args) + ["--settings", settings, "--permission-mode", agent.permission_mode]
    if agent.model:
        args += ["--model", agent.model]
    for directory in agent.existing_plugin_dirs():
        args += ["--plugin-dir", str(directory)]
    args += ["--plugin-dir", str(PLUGIN_DIR)]
    return args


def turn_command(claude: str, agent: Agent, settings: str, session_id: Optional[str], prompt: str) -> list:
    """One non-interactive turn, resumed when the conversation has a session. The prompt goes last."""
    cmd = [claude, "-p", "--output-format", "json", *launch_args(agent, settings)]
    if session_id:
        cmd += ["--resume", session_id]
    cmd.append(prompt)
    return cmd


@dataclass
class Outcome:
    ok: bool
    detail: str
    session_id: Optional[str] = None


_SUBTYPE = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")


def outcome(rc: Optional[int], stdout: bytes) -> Outcome:
    """Whether a finished run was a finished turn. The detail never quotes the run's output, which is
    the reply or an echo of the prompt."""
    try:
        result = json.loads(stdout)
        if not isinstance(result, dict):
            raise ValueError
    except ValueError:
        return Outcome(False, f"exit {rc}, and the output was not a result ({len(stdout)} bytes)")
    session_id = result.get("session_id") if isinstance(result.get("session_id"), str) else None
    if rc != 0:
        return Outcome(False, f"exit {rc}", session_id)
    if result.get("is_error"):
        subtype = result.get("subtype")
        kind = subtype if isinstance(subtype, str) and _SUBTYPE.match(subtype) else "error"
        return Outcome(False, f"the run reported an error ({kind})", session_id)
    return Outcome(True, "", session_id)
