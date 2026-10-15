"""turn_runner calls the installed turn runner with the arguments it accepts. A stub runner
records its argv, so this needs neither claude nor a desk."""
import json
import os
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hearth_host import turn_runner  # noqa: E402


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
