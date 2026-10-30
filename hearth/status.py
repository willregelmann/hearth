"""What one agent's running process reports about itself to something outside it
(docs/interfaces/STATUS.md), served by Hearth's host over gRPC on a Unix socket.

What holds:
  - Status reports. Get reads the host's own state, the desk's ledger and the turn ledger, and
    writes nothing: it never wakes a conversation, takes a message or touches the home.
  - The agent runs the same whether or not anything reads it. The host serves it beside its
    turns; if it can't be served, the host logs that and carries on (host.serve).
  - Nothing said in a thread is in a report: pending wakes are counts, recent turns come from the
    turn ledger, which holds no prompt or reply text (home/turn).
  - Only whoever can enter the socket's directory can connect, so the server refuses a
    directory anyone else can enter. A reader the board's user is granted is a group grant on
    that directory, never a world one.
  - A report it can't give is named in not_reported with why, so an empty list is never
    mistaken for "none".
"""
import json
import logging
import math
import os
import stat
import time
from pathlib import Path

import grpc

from frontdesk import wire
from hearth import status_pb2 as pb
from hearth import status_pb2_grpc as rpc

logger = logging.getLogger("hearth.status")

RECENT = 20
TAIL_BYTES = 256 * 1024

NOT_BUILT = (
    ("faculties", "not built: this process doesn't run the faculty check"),
    ("last sweep", "not built: intentions have no sweep yet"),
    ("live turns in sessions opened outside this process",
     "only this process's own turns are listed; a session open elsewhere shows on its pending wake"),
)


class StatusError(Exception):
    pass


class Reporter(rpc.StatusServicer):
    def __init__(self, host, agent: str, turn_ledger: Path, *, recent: int = RECENT):
        self.host, self.agent, self.turn_ledger, self.recent = host, agent, Path(turn_ledger), recent

    async def Get(self, request, context) -> pb.Report:
        return self.report()

    def report(self) -> pb.Report:
        r = pb.Report(agent=self.agent, as_of=time.time())
        for thread, started in sorted(self.host.live.items()):
            r.live_turns.add(thread=thread, started=started)
        self._pending(r)
        self._recent(r)
        for report, reason in NOT_BUILT:
            r.not_reported.add(report=report, reason=reason)
        return r

    def _pending(self, r: pb.Report) -> None:
        waiting: dict[str, int] = {}
        try:
            ledger = self.host.desk.ledger
            for channel in ledger.live_channels():
                n = sum(json.loads(row["arrival"]).get("arrive") == wire.WAKE
                        for row in ledger.pending(channel["handle"]))
                if n:
                    waiting[channel["conversation"]] = waiting.get(channel["conversation"], 0) + n
        except Exception as exc:
            r.not_reported.add(report="waiting messages", reason=f"the desk's ledger couldn't be read: {exc}")
        now_mono, now = time.monotonic(), time.time()
        threads = set(waiting) | set(self.host.deferred) | set(self.host.failed)
        for thread in sorted(threads):
            failures, due = self.host.failed.get(thread, (0, 0.0))
            retry_at = 0.0 if not failures or math.isinf(due) else now + max(due - now_mono, 0.0)
            r.pending_wakes.add(thread=thread, waiting=waiting.get(thread, 0),
                                open_elsewhere=thread in self.host.deferred,
                                failures=failures, retry_at=retry_at)

    def _recent(self, r: pb.Report) -> None:
        try:
            with open(self.turn_ledger, "rb") as f:
                f.seek(0, os.SEEK_END)
                f.seek(max(f.tell() - TAIL_BYTES, 0))
                lines = f.read().decode("utf-8", "replace").splitlines()
        except FileNotFoundError:
            return   # no turn has run yet
        except OSError as exc:
            r.not_reported.add(report="recent turns", reason=f"the turn ledger couldn't be read: {exc}")
            return
        rows = []
        for line in lines:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue   # the first line of a tail is usually cut
        for row in rows[-self.recent:]:
            r.recent_turns.add(thread=row.get("resume") or row.get("session_id") or "",
                               trigger=row.get("trigger") or "",
                               started=row.get("ts_start_epoch") or 0.0,
                               ended=row.get("ts_end_epoch") or 0.0,
                               ok=row.get("rc") == 0 and not row.get("error"),
                               error=row.get("error") or "")


async def serve(reporter: Reporter, path: Path) -> grpc.aio.Server:
    """Serve ``reporter`` on a Unix socket at ``path``. Refuses a directory anyone else can enter."""
    path = Path(path)
    private_dir(path.parent)
    if path.is_socket():
        path.unlink()   # left by a host that didn't stop cleanly
    server = grpc.aio.server()
    rpc.add_StatusServicer_to_server(reporter, server)
    try:
        server.add_insecure_port(f"unix:{path}")
    except RuntimeError as exc:
        raise StatusError(f"{path}: {exc}") from exc
    await server.start()
    path.chmod(0o660)   # the directory decides who reaches it; the board's grant is its group
    return server


def private_dir(d: Path) -> None:
    """Refuse a directory every user can enter: a socket in it would be anyone's to read."""
    try:
        st = Path(d).stat()
    except OSError as exc:
        raise StatusError(f"{d}: {exc}") from exc
    if st.st_mode & stat.S_IRWXO:
        raise StatusError(f"{d} is open to every user ({stat.filemode(st.st_mode)})")
