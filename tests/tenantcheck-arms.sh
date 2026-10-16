#!/bin/bash
# Mutation arms for hearth/tenantcheck.py and hearth/marketplace.py: each removes one guard and must
# turn a test red. cmp-guarded: every source is restored and checked byte-identical after each arm.
set -u
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
# Same baseline as tests/mutation-arms.sh (#66).
"$PY" -c 'import sys' >/dev/null 2>&1 || { echo "FATAL: PY=$PY is not a usable interpreter" >&2; exit 2; }
"$PY" -m pytest -q -p no:cacheprovider tests/ >/dev/null 2>&1 || { echo "FATAL: the UNARMED suite is not green under PY=$PY" >&2; exit 2; }
red=0; bad=0
# arm()'s cmp-guarded restore sits on its normal path, so a signal between the mutation and
# the restore leaves the mutated source on disk, where it reads as a real defect in reviewed
# code. $B is local to arm(), so the in-flight pair is published to CUR_F/CUR_B for the trap.
# SIGKILL cannot be trapped; this covers TERM/INT/HUP and the ordinary exit paths.
CUR_F=""; CUR_B=""
restore() {
  if [ -n "${CUR_B:-}" ] && [ -f "$CUR_B" ]; then
    if [ -z "${CUR_F:-}" ]; then
      echo "RESTORE FAILED: subject unknown, backup kept at $CUR_B" >&2
      return 1
    fi
    cp -p "$CUR_B" "$CUR_F"
    if cmp -s "$CUR_B" "$CUR_F"; then
      rm -f "$CUR_B"
    else
      echo "RESTORE FAILED $CUR_F: backup kept at $CUR_B" >&2
      return 1
    fi
  fi
  CUR_F=""; CUR_B=""
  return 0
}
trap restore EXIT
trap 'trap - EXIT; if restore; then echo "INTERRUPTED: restored $CUR_F" >&2; else echo "INTERRUPTED: $CUR_F NOT restored" >&2; fi; exit 130' TERM INT HUP
arm() {
  local name="$1" F="$2" old="$3" new="$4" B
  local _g=0 _n=0 _t
  # A green arm is re-run (#99): one green is weak evidence and must not look
  # identical to a repeated one. Red on any trial means the guard is live.
  for _t in 1 2 3; do
    B=$(mktemp); cp -p "$F" "$B"
    CUR_F="$F"; CUR_B="$B"
    $PY - "$F" "$old" "$new" <<'EOF' || { echo "ARM $name: ANCHOR NOT FOUND, nothing mutated"; cp -p "$B" "$F"; cmp -s "$B" "$F" || echo "RESTORE FAILED $F"; rm -f "$B"; exit 3; }
import sys; p, old, new = sys.argv[1:]; s = open(p).read()
assert s.count(old) == 1, f"anchor not unique: {old!r}"
want = s.replace(old, new)
with open(p, "w") as fh: fh.write(want)
assert open(p).read() == want, f"mutation did not land on disk: {p}"
EOF
    L=$(mktemp); timeout 300 $PY -m pytest -q -p no:cacheprovider tests/test_tenantcheck.py >"$L" 2>&1; prc=$?
    out=$(tail -1 "$L"); rm -f "$L"
    cp -p "$B" "$F"; cmp -s "$B" "$F" || { echo "RESTORE FAILED $F"; exit 2; }; rm -f "$B"
    _n=$_t
    [ $prc = 1 ] && break
    [ $prc = 0 ] || break
    _g=$((_g+1))
  done
  if [ $prc = 1 ] && [ $_g = 0 ]; then echo "ARM $name: RED ($out)"; red=$((red+1));
  elif [ $prc = 1 ]; then echo "ARM $name: FLAKY, $_g green of $_n trials ($out)"; bad=$((bad+1));
  elif [ $prc = 0 ]; then echo "ARM $name: GREEN ($_g/$_n) ($out)"; bad=$((bad+1));
  else echo "ARM $name: NOT A RESULT, pytest rc=$prc ($out)"; bad=$((bad+1)); fi
}
T=hearth/tenantcheck.py; M=hearth/marketplace.py
arm "trust gitCommitSha, skip the tree" $T \
  '                diffs = plugintree.compare(ref, installed)' '                diffs = []'
arm "compare against the export named by the installed version, not the pin" $T \
  '    ref = t.ref / name / want["commit"]' '    ref = t.ref / name / sorted(os.listdir(t.ref / name))[0]'
arm "settings marketplace path not checked" $T \
  '    if (s.get("extraKnownMarketplaces") or {}).get(marketplace.NAME, {}).get("source") != src:' '    if False:'
arm "records marketplace path not checked" $T \
  '    if k.get("source") != src or k.get("installLocation") != t.mkt:' '    if False:'
arm "enabled not checked" $T \
  '    if (s.get("enabledPlugins") or {}).get(pid) is not True:' '    if False:'
arm "any number of install records" $T \
  'or len(entries) != 1 or' 'or'
arm "any scope" $T \
  '        if e.get("scope") != "user":' '        if False:'
arm "installPath trusted as recorded" $T \
  '        elif e.get("installPath") != str(expect):' '        elif False:'
arm "version not checked for traversal" $T \
  '        if not isinstance(ver, str) or not ver or "/" in ver or ver in (".", ".."):' '        if False:'
arm "links on the install path allowed" $T \
  '        if links:' '        if False:'
arm "root's side writability not checked" $T \
  '        if w:' '        if False:'
arm "interpreter from the login env, not the plugin's config" $T \
  '        "CLAUDE_PLUGIN_OPTION_PYTHON": opts.get("python")}' '        "CLAUDE_PLUGIN_OPTION_PYTHON": "python3"}'
arm "interpreter problems dropped" $T \
  '    found += problems' '    pass'
arm "unset frontdesk home passes" $T \
  '        return PENDING, (f"frontdesk home unset' '        return GREEN, (f"frontdesk home unset'
arm "frontdesk home outside the tenant's home" $T \
  '    if real == h or not real.is_relative_to(h):' '    if False:'
arm "other plugins silent" $T \
  '        return KNOWN, f"enabled outside' '        return GREEN, f"enabled outside'
arm "settings read through a link" $T \
  '        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)' '        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)'
arm "no size bound" $T \
  '    if len(raw) > _BOUND:' '    if False:'
arm "settings.local.json ignored" $T \
  '        local = load(self.cfg / "settings.local.json")' '        local = None'
arm "settings.local.json loses to settings.json" $T \
  '        return _merge(s, local)' '        return _merge(local, s)'
arm "frontdesk home judged by string prefix of the unresolved home" $T \
  '    if real == h or not real.is_relative_to(h):' '    if not str(real).startswith(str(t.home) + "/"):'
arm "access() on the link itself (the Buster false RED)" $T \
  '    return [str(q) for q in found if os.access(q, os.W_OK)]' '    return [str(q) for q in found if os.access(q, os.W_OK)] + ([str(p)] if Path(p).is_symlink() and os.access(p, os.W_OK, follow_symlinks=False) else [])'
arm "the final target not checked" $T \
  '        cur = nxt
        add(cur)' '        cur = nxt
        add(cur) if parts else None'
arm "a link met at an ancestor collapsed by realpath (#85 R1)" $T \
  '        if nxt.is_symlink():' '        if nxt.is_symlink() and not parts:
            cur = Path(os.path.realpath(nxt)); add(cur); continue
        if nxt.is_symlink():'
arm "the path normalised as typed before resolving links" $T \
  '    start = Path(p) if os.path.isabs(p) else Path.cwd() / p' '    start = Path(os.path.normpath(Path(p) if os.path.isabs(p) else Path.cwd() / p))'
arm "marketplace overwrites a different file" $M \
  '        raise RuntimeError(f"{path} exists and differs' '        return "present"; raise RuntimeError(f"{path} exists and differs'
arm "marketplace serves an extra pin" $M \
  '    if set(p) != set(PLUGINS):' '    if False:'
arm "host_running: any process owner" $T \
  '    if uid != os.getuid():' '    if False:'
arm "host_running: any code in the main process" $T \
  '    if argv[:4] != [HEARTH_PY.encode(), b"-I", b"-m", b"hearth.host"]:' '    if False:'
arm "host_running: a unit file the tenant can write" $T \
  '    if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:' '    if not stat.S_ISREG(st.st_mode):'
arm "host_running: a unit from anywhere" $T \
  '    if s.get("FragmentPath") != want:' '    if False:'
arm "host_running: not running is fine" $T \
  '    if s.get("ActiveState") != "active" or s.get("MainPID", "0") == "0":' '    if s.get("MainPID", "0") == "0":'
echo "arms red: $red, arms bad: $bad"; [ "$bad" = 0 ]
