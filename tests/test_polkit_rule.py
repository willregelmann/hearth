"""home/hearth-board.rules (docs/interfaces/BOARD.md, docs/decisions/0013): the board's user may
restart one agent's host unit, and nothing else to any unit. The rule is polkit's JavaScript, run
here under node with polkit's side of the call faked: what this checks is the rule's own answer
for each request, not that polkit loads it (that needs a host with polkit; see the PR)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

RULE = Path(__file__).parent.parent / "home" / "hearth-board.rules"
HARNESS = """
const fs = require("fs");
let rule;
const polkit = {Result: {YES: "yes", NO: "no", AUTH_ADMIN: "auth_admin"}, addRule: f => { rule = f; }};
eval(fs.readFileSync(process.argv[1], "utf8"));
const cases = JSON.parse(process.argv[2]);
console.log(JSON.stringify(cases.map(([id, user, verb, unit]) =>
  rule({id, lookup: k => ({verb, unit})[k]}, {user}) || null)));
"""
MANAGE = "org.freedesktop.systemd1.manage-units"


def answers(cases):
    node = shutil.which("node")
    assert node, "node is needed to run the polkit rule"
    out = subprocess.run([node, "-e", HARNESS, str(RULE), json.dumps(cases)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_the_board_may_restart_an_agent_s_host_and_nothing_else():
    allowed = [[MANAGE, "hearth-board", "restart", "hearth-host@alice.service"],
               [MANAGE, "hearth-board", "restart", "hearth-host@wren-2.service"]]
    refused = [
        [MANAGE, "hearth-board", "stop", "hearth-host@alice.service"],
        [MANAGE, "hearth-board", "start", "hearth-host@alice.service"],
        [MANAGE, "hearth-board", "restart", "hearth-board.service"],
        [MANAGE, "hearth-board", "restart", "sshd.service"],
        [MANAGE, "hearth-board", "restart", "hearth-host@.service"],
        [MANAGE, "hearth-board", "restart", "hearth-host@alice.service hearth-host@bob.service"],
        [MANAGE, "hearth-board", "restart", "hearth-host@alice.service.d"],
        [MANAGE, "hearth-board", "restart", None],
        [MANAGE, "alice", "restart", "hearth-host@bob.service"],
        [MANAGE, "caddy", "restart", "hearth-host@alice.service"],
        ["org.freedesktop.systemd1.manage-unit-files", "hearth-board", "restart", "hearth-host@alice.service"],
        ["org.freedesktop.login1.reboot", "hearth-board", None, None],
    ]
    assert answers(allowed) == ["yes", "yes"]
    assert answers(refused) == [None] * len(refused)
