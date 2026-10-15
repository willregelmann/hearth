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
arm() {
  local name="$1" F="$2" old="$3" new="$4" B
  B=$(mktemp); cp -p "$F" "$B"
  $PY - "$F" "$old" "$new" <<'EOF' || { echo "ARM $name: ANCHOR NOT FOUND, nothing mutated"; cp -p "$B" "$F"; rm -f "$B"; exit 3; }
import sys; p, old, new = sys.argv[1:]; s = open(p).read()
assert s.count(old) == 1, f"anchor not unique: {old!r}"; open(p, "w").write(s.replace(old, new))
EOF
  out=$(timeout 300 $PY -m pytest -q -p no:cacheprovider tests/test_tenantcheck.py 2>&1 | tail -1)
  cp -p "$B" "$F"; cmp -s "$B" "$F" || { echo "RESTORE FAILED $F"; exit 2; }; rm -f "$B"
  if echo "$out" | grep -qE "failed|error"; then echo "ARM $name: RED ($out)"; red=$((red+1)); else echo "ARM $name: GREEN ($out)"; bad=$((bad+1)); fi
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
arm "marketplace overwrites a different file" $M \
  '        raise RuntimeError(f"{path} exists and differs' '        return "present"; raise RuntimeError(f"{path} exists and differs'
arm "marketplace serves an extra pin" $M \
  '    if set(p) != set(PLUGINS):' '    if False:'
echo "arms red: $red, arms green: $bad"; [ "$bad" = 0 ]
