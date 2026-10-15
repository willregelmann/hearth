# A plugin pin has two sources of truth, and the installed one wins at run time

## Context and Problem Statement

Hearth pins its plugins — Front Desk and Tapestry — to exact commits. Until [ADR-0009](0009-tapestry-and-front-desk-are-pinned-imports-front-desk-carries-agent-traffic-now.md) landed, `hearth/pins.py` read those pins from `pyproject.toml` by walking up from the module's own file. That works in a source checkout and fails in a non-editable install: `pyproject.toml` is not installed beside the package, so `pins()` raised `FileNotFoundError` on `site-packages/pyproject.toml` — the failure that `/opt/hearth/venv` would hit on every call.

The fix read the pins from the installed distribution's metadata instead, falling back to `pyproject.toml` when the distribution is not installed. That makes a non-editable install work, which is the case Hearth is deployed in.

It also means the same fact now has two sources: the metadata recorded when the wheel was built, and the `pyproject.toml` in the working tree. They agree whenever the installed version matches the tree. They diverge whenever it does not, and nothing in the system detects that.

## Decision Drivers

* `/opt/hearth/venv` is a non-editable install and is the deployment target, so a pin that only resolves in a source tree is not usable.
* A pin is a provenance claim. A wrong answer about which commit is pinned is worse than no answer, because the caller cannot tell it is wrong.
* The previous behaviour failed loudly. The new behaviour can answer confidently from a stale snapshot. Loudness was traded away and the trade should be recorded rather than discovered.

## Considered Options

* Read from installed metadata, fall back to `pyproject.toml`. (What shipped.)
* Read from `pyproject.toml` only, and require an editable install everywhere.
* Read both and raise when they disagree.

## Decision Outcome

Installed metadata is authoritative at run time; `pyproject.toml` is authoritative at build time. When the distribution is installed, `pins()` answers from its metadata and does not consult the tree.

This is accepted as a trade, not as a pure improvement. The divergence it permits is silent: there is no check, and a caller cannot distinguish a pin read from a current install from one read from a stale snapshot.

### Consequences

* Good, because `pins()` resolves in a non-editable install, which is how Hearth is actually deployed.
* Good, because the pin a running Hearth reports is the pin it was built with, which is the honest answer for provenance.
* Bad, because editing `pyproject.toml` without reinstalling changes nothing that `pins()` reports, and reports nothing. Measured: rewriting Tapestry's pin to `deadbeef` in the tree, with no reinstall, left `pins()` returning the previous commit with no warning. Before this change the same situation raised `FileNotFoundError`.
* Bad, because the two sources agreeing today is not a property the code maintains. It was verified once, by hand, at the commit that introduced the fallback.
* Bad, because there is a third source, and it makes the answer depend on the working directory. `importlib.metadata` resolves a distribution by scanning `sys.path`, and an editable install writes a `hearth.egg-info` into the source tree, which `''`/cwd puts ahead of `site-packages`. So after `pip install -e .` the same interpreter and the same install answer differently depending on where the process starts, and `pins()` reports whichever of the two was written last rather than whichever is true. Neither side is reliably the stale one. Measured both ways: with the in-tree `egg-info` regenerated after the edit, `pins()` returns `deadbeef…` from the tree and the original commit from `/tmp`; with the `egg-info` left untouched and only the installed `dist-info` rebuilt, the directions swap. A clean non-editable install has no `egg-info` and is consistent from both.
* Bad, because a reinstall is not reliably a rebuild. `pip install .` after a `pyproject.toml` edit can reuse a cached wheel and leave the installed metadata at the previous pin; `--no-cache-dir --force-reinstall` was needed to make it reflect the edit. So "I reinstalled" is not evidence that the installed pin changed.
* Neutral, because a source checkout that is not editable-installed behaves as it did before.

## Confirmation

A reader who needs to know which commit a given Hearth is pinned to reads it from the installed distribution, from a process started outside the source tree, so an in-tree `egg-info` cannot answer in its place. Whether that `egg-info` is newer or older than the installed metadata is not knowable from the answer, which is why the location of the read is the rule rather than a judgement about which copy to trust.

Anyone changing a pin changes `pyproject.toml` and reinstalls. A pin edit without a reinstall is not a pin change; it is a divergence, and the archive now says so rather than leaving it to be found.
