#!/bin/bash
# Mutation arms for home/venv-state and provision's venv block (#86): each removes one guard, and
# home/venv-controls must fail. Sources are restored and checked byte-identical after every arm.
set -u
cd "$(dirname "$0")/.."
bash home/venv-controls >/dev/null 2>&1 || { echo "FATAL: venv-controls is not green unarmed" >&2; exit 2; }
red=0; bad=0; F=; B=
restore() { if [ -n "${B:-}" ] && [ -f "$B" ]; then cp -p "$B" "$F"; rm -f "$B"; fi; return 0; }
trap restore EXIT
trap 'restore; echo "INTERRUPTED: restored $F" >&2; exit 130' TERM INT HUP
arm() {
  local name="$1" old="$3" new="$4"; F=$2; B=$(mktemp); cp -p "$F" "$B"
  python3 - "$F" "$old" "$new" <<'EOF' || { echo "ARM $name: ANCHOR NOT FOUND, nothing mutated"; restore; exit 3; }
import sys; p, old, new = sys.argv[1:]; s = open(p).read()
assert s.count(old) == 1, f"anchor not unique: {old!r}"; open(p, "w").write(s.replace(old, new))
EOF
  out=$(bash home/venv-controls 2>&1); rc=$?
  cp -p "$B" "$F"; cmp -s "$B" "$F" || { echo "RESTORE FAILED $F"; exit 2; }; rm -f "$B"; B=
  if [ $rc != 0 ]; then echo "ARM $name: RED ($(echo "$out" | grep -c '^FAIL') FAIL)"; red=$((red+1)); else echo "ARM $name: GREEN"; bad=$((bad+1)); fi
}
V=home/venv-state; P=home/provision
arm "hearth files not compared" $V \
  '        elif _sha(want[rel]) != _sha(have[rel]):' '        elif False:'
arm "pins not compared" $V \
  '        if got != m.group(1):' '        if False:'
arm "extra installed files ignored" $V \
  '        elif rel not in want:' '        elif False:'
arm "two installed dists of one name accepted (first wins)" $V \
  '    if len(found) != 1:' '    if not found:'
arm "an unexpected error reads as 'differs'" $V \
  '        return 2
    for d in diffs:' '        return 1
    for d in diffs:'
arm "provision treats a difference as present" $P \
  '         die "$VENV differs from this checkout:' '         echo "$VENV differs from this checkout:'
arm "provision skips the re-check after --upgrade" $P \
  '             || die "$VENV still differs after --upgrade:' '             || echo "$VENV still differs after --upgrade:'
arm "provision upgrades when it couldn't compare" $P \
  '    *) die "couldn'"'"'t compare $VENV' '    *) run "$HPY" -m pip install --quiet "$repo"; die "couldn'"'"'t compare $VENV'
echo "arms red: $red, arms green: $bad"; [ "$bad" = 0 ]
