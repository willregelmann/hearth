"""The other end of the gateway's socket (docs/interfaces/PUSH.md): one JSON request, one JSON response."""
import json
import socket
from typing import Optional

from hearth.home import Home


class GatewayUnavailable(Exception):
    pass


def request(home: Home, payload: dict, timeout: Optional[float] = 30.0) -> dict:
    """Send a request and return the response, which is ``{"ok": true, ...}`` or ``{"ok": false,
    "error": ...}``. Raises GatewayUnavailable when nothing answers on the socket."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        try:
            sock.connect(str(home.socket))
        except (FileNotFoundError, ConnectionRefusedError):
            raise GatewayUnavailable(f"the gateway is not running (nothing is listening on {home.socket})") from None
        except OSError as exc:
            raise GatewayUnavailable(f"cannot reach the gateway at {home.socket}: {exc.strerror or exc}") from None
        try:
            sock.sendall(json.dumps(payload).encode() + b"\n")
        except (BrokenPipeError, ConnectionResetError):
            pass   # the gateway answered before it had it all; its answer says why
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
            if chunk.endswith(b"\n"):
                break
    except socket.timeout:
        raise GatewayUnavailable("the gateway did not answer in time") from None
    finally:
        sock.close()
    data = b"".join(chunks)
    try:
        response = json.loads(data)
    except ValueError:
        raise GatewayUnavailable("the gateway sent something that is not a response") from None
    if not isinstance(response, dict):
        raise GatewayUnavailable("the gateway sent something that is not a response")
    return response
