#!/bin/bash
# Mutation arms for provision's link repoint on a pin move (home/store-controls, last block): each
# breaks one property of the link block, and store-controls must fail. The source is restored and
# checked byte-identical after every arm (and on a signal).
set -u
cd "$(dirname "$0")/.."
F=home/provision
bash home/store-controls >/dev/null 2>&1 || { echo "FATAL: store-controls is not green unarmed" >&2; exit 2; }
B=$(mktemp); cp -p $F $B
restore() { if [ -n "${B:-}" ] && [ -f "$B" ]; then cp -p "$B" "$F"; if cmp -s "$B" "$F"; then rm -f "$B"; else echo "RESTORE FAILED $F: backup kept at $B" >&2; return 1; fi; fi; return 0; }
trap restore EXIT
trap 'trap - EXIT; if restore; then echo "INTERRUPTED: restored $F" >&2; else echo "INTERRUPTED: $F NOT restored" >&2; fi; exit 130' TERM INT HUP
red=0; bad=0
arm() {
  local name="$1" old="$2" new="$3"
  python3 - "$F" "$old" "$new" <<'EOF' || { echo "ARM $name: ANCHOR NOT FOUND, nothing mutated"; cp -p "$B" "$F"; cmp -s "$B" "$F" || echo "RESTORE FAILED $F" >&2; exit 3; }
import sys; p, old, new = sys.argv[1:]; s = open(p).read()
assert s.count(old) == 1, f"anchor not unique: {old!r}"
want = s.replace(old, new)
with open(p, "w") as fh: fh.write(want)
assert open(p).read() == want, f"mutation did not land on disk: {p}"
EOF
  out=$(bash home/store-controls 2>&1); rc=$?
  cp -p $B $F; cmp -s $B $F || { echo "RESTORE FAILED"; exit 2; }
  n=$(echo "$out" | grep -c '^FAIL')
  if [ "$n" -gt 0 ]; then echo "ARM $name: RED ($n FAIL)"; red=$((red+1))
  elif [ $rc != 0 ]; then echo "ARM $name: NOT A RESULT, controls rc=$rc with no FAIL line -- broken, not caught"; bad=$((bad+1))
  else echo "ARM $name: GREEN"; bad=$((bad+1)); fi
}
arm "a stale link is never repointed (the old STOP)" \
  'elif [ -L "$link" ] && other=$(readlink "$link") && [ "$(dirname "$other")" = "$vdir" ] \' 'elif false \'
arm "any link is repointed, wherever it points" \
  '[ "$(dirname "$other")" = "$vdir" ] \' 'true \'
arm "any name in the versions dir is repointed, version number or not" \
  "grep -Eq '^[0-9]+\\.[0-9]+\\.[0-9]+\$'; then" "true; then"
arm "a non-link in the way is replaced" \
  'elif tq test -e "$link" || [ -L "$link" ]; then die "$link exists and isn'"'"'t the pinned link"' 'elif tq test -e "$link" || [ -L "$link" ]; then as_t ln -sfn "$dst" "$link"'
arm "the repoint is printed but never done" \
  '  as_t ln -sfn "$dst" "$link"
elif' '  true
elif'
arm "the repoint ignores a dry run (runs outside as_t)" \
  '  as_t ln -sfn "$dst" "$link"
elif' '  ln -sfn "$dst" "$link"
elif'
echo "arms red: $red, arms bad: $bad"; [ "$bad" = 0 ]
