"""Running child programs, and telling whether a process is still the one that was recorded."""
import asyncio
import os
import signal
import subprocess
from dataclasses import dataclass
from typing import Callable, Mapping, Optional, Sequence


def start_time(pid: int) -> Optional[str]:
    """When a process started, as ``ps`` prints it, which both macOS and Linux do the same way.
    None when there is no such process or ``ps`` can't say."""
    try:
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                             env={**os.environ, "LC_ALL": "C"}, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def is_same_process(pid: int, started: Optional[str]) -> bool:
    """True while ``pid`` is the process that was recorded with start time ``started``. A process
    that exists but whose start can't be read counts as the same one: the callers would rather wait
    for a dead process than act beside a live one."""
    if not exists(pid):
        return False
    if not started:
        return True
    now = start_time(pid)
    return now is None or now == started


def kill_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


@dataclass
class Ran:
    rc: Optional[int]
    stdout: bytes = b""
    stderr_bytes: int = 0
    timed_out: bool = False
    error: Optional[str] = None


async def run(argv: Sequence[str], *, cwd: str, env: Mapping[str, str], timeout: float,
              on_start: Optional[Callable[[int], None]] = None) -> Ran:
    """Run a program with nothing on its standard input, in a process group of its own so that a
    timeout, or a cancelled caller, kills it and everything it started. Its standard error is only
    counted: it can echo what the program was shown."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, cwd=cwd, env=dict(env), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, start_new_session=True)
    except OSError as exc:
        return Ran(rc=None, error=f"could not run {os.path.basename(argv[0])}: {exc.strerror or exc}")
    if on_start is not None:
        on_start(proc.pid)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        kill_group(proc.pid)
        await proc.wait()
        return Ran(rc=None, timed_out=True)
    except BaseException:
        kill_group(proc.pid)
        await proc.wait()
        raise
    return Ran(rc=proc.returncode, stdout=out, stderr_bytes=len(err))
