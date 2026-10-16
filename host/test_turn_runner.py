"""turn_runner calls the installed turn runner with the arguments it accepts. A stub runner
records its argv, so this needs neither claude nor a desk."""
import json
import os
import stat
import sys
from pathlib import Path

import logging

from hearth.host import configure_logging, turn_runner  # noqa: E402


def test_turn_runner_resumes_the_conversation_with_the_prompt(tmp_path):
    out = tmp_path / "argv.json"
    stub = tmp_path / "turn"
    stub.write_text(f"#!{sys.executable}\nimport json, sys\njson.dump(sys.argv[1:], open({str(out)!r}, 'w'))\n")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    rc = turn_runner("session-A", "<frontdesk from=\"ember\">\nnote\n</frontdesk>", turn=str(stub), timeout=900)
    assert rc == 0
    argv = json.loads(out.read_text())
    assert argv[:4] == ["--trigger", "frontdesk", "--resume", "session-A"]
    assert argv[argv.index("--timeout") + 1] == "900"
    assert argv[-1].startswith("<frontdesk")


def test_turn_runner_returns_the_runners_failure(tmp_path):
    stub = tmp_path / "turn"
    stub.write_text("#!/bin/sh\nexit 3\n")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    assert turn_runner("session-A", "x", turn=str(stub)) == 3


def test_the_turn_s_reply_never_reaches_the_host_s_stdout(tmp_path, capfd):
    """The host's stdout is the system journal; the reply belongs in the tenant's home only."""
    stub = tmp_path / "turn"
    stub.write_text("#!/bin/sh\necho REPLY-TEXT-SECRET\necho 'turn: one-line error' >&2\n")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    assert turn_runner("session-A", "x", turn=str(stub)) == 0
    out, err = capfd.readouterr()
    assert "REPLY-TEXT-SECRET" not in out + err
    assert "turn: one-line error" in err   # the runner's own errors still reach the journal


def test_http_client_logging_is_warning_and_hearth_is_info():
    # The levels configure_logging sets itself, from NOTSET: an effective level would come from
    # whatever the root logger already is (pytest's), and pass without the code doing anything.
    for name in ("httpx", "httpcore", "hearth"):
        logging.getLogger(name).setLevel(logging.NOTSET)
    configure_logging()
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
    assert logging.getLogger("hearth").level == logging.INFO
    assert logging.getLogger("hearth.host").getEffectiveLevel() == logging.INFO
