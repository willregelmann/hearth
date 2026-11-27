"""Running child programs, and telling whether a process is still the one that was recorded."""
import asyncio
import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence


PROC = Path("/proc")
HAVE_PROC = (PROC / "self" / "stat").exists()


def _proc_stat(pid: int) -> Optional[list]:
    """The fields of ``/proc/<pid>/stat`` after the command name, which may itself hold spaces and
    parentheses. None when there is no such process."""
    try:
        text = (PROC / str(pid) / "stat").read_text()
    except OSError:
        return None
    return text[text.rindex(")") + 2:].split()


def _proc_start(pid: int) -> Optional[str]:
    fields = _proc_stat(pid)
    return f"proc:{fields[19]}" if fields and len(fields) > 19 else None


def _ps_start(pid: int) -> Optional[str]:
    try:
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                             env={**os.environ, "LC_ALL": "C"}, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def start_time(pid: int) -> Optional[str]:
    """When a process started, read from ``/proc`` where it exists (tagged ``proc:``) and from ``ps``
    elsewhere (docs/decisions/0021). None when there is no such process or it can't be read."""
    return _proc_start(pid) if HAVE_PROC else _ps_start(pid)


def _start_like(pid: int, recorded: str) -> Optional[str]:
    """The start of ``pid``, read the same way ``recorded`` was, so the two can be compared."""
    return _proc_start(pid) if recorded.startswith("proc:") else _ps_start(pid)


def exists(pid: int) -> bool:
    """Whether a process with this id is alive. One that has exited but not been reaped is not."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    if HAVE_PROC:
        fields = _proc_stat(pid)
        if fields is None or fields[0] in ("Z", "X"):
            return False
    return True


def is_same_process(pid: int, started: Optional[str]) -> bool:
    """True while ``pid`` is the process that was recorded with start time ``started``. A process
    that exists but whose start can't be read counts as the same one: the callers would rather wait
    for a dead process than act beside a live one."""
    if not exists(pid):
        return False
    if not started:
        return True
    now = _start_like(pid, started)
    return now is None or now == started


def is_recorded_process(pid: int, started: Optional[str]) -> bool:
    """True only when ``pid`` is alive and provably the process recorded at ``started``: for killing,
    where a wrong yes would hit an unrelated process."""
    return bool(started) and exists(pid) and _start_like(pid, started) == started


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
        if not os.path.isdir(cwd):
            return Ran(rc=None, error=f"the working directory {cwd} does not exist, so {os.path.basename(argv[0])} "
                                      "could not be started there")
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
