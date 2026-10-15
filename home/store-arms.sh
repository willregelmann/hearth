#!/bin/bash
# Mutation arms for provision's step 3 store (#60): each removes one guard, and home/store-controls
# must fail. The source is restored and checked byte-identical after every arm (and on a signal).
set -u
cd "$(dirname "$0")/.."
F=home/provision
bash home/store-controls >/dev/null 2>&1 || { echo "FATAL: store-controls is not green unarmed" >&2; exit 2; }
B=$(mktemp); cp -p $F $B
restore() { if [ -n "${B:-}" ] && [ -f "$B" ]; then cp -p "$B" "$F"; rm -f "$B"; fi; return 0; }
trap restore EXIT
trap 'restore; echo "INTERRUPTED: restored $F" >&2; exit 130' TERM INT HUP
red=0; bad=0
arm() {
  local name="$1" old="$2" new="$3"
  python3 - "$F" "$old" "$new" <<'EOF' || { echo "ARM $name: ANCHOR NOT FOUND, nothing mutated"; cp -p "$B" "$F"; exit 3; }
import sys; p, old, new = sys.argv[1:]; s = open(p).read()
assert s.count(old) == 1, f"anchor not unique: {old!r}"; open(p, "w").write(s.replace(old, new))
EOF
  out=$(bash home/store-controls 2>&1); rc=$?
  cp -p $B $F; cmp -s $B $F || { echo "RESTORE FAILED"; exit 2; }
  if [ $rc != 0 ]; then echo "ARM $name: RED ($(echo "$out" | grep -c '^FAIL') FAIL)"; red=$((red+1)); else echo "ARM $name: GREEN"; bad=$((bad+1)); fi
}
arm "stored file's hash not checked" \
  '  sha_ok "$CLAUDE_SRC" || die' '  true || die'
arm "download's hash not checked" \
  '  sha_ok "$part" || { rm -f' '  true || { rm -f'
arm "stored file's owner and mode not checked" \
  '  [ -f "$CLAUDE_SRC" ] && rootish "$CLAUDE_SRC" \' '  [ -f "$CLAUDE_SRC" ] \'
arm "store dir not checked" \
  '  [ -d "$CLAUDE_STORE" ] && rootish "$CLAUDE_STORE" || die' '  true || die'
arm "failed download leaves its part" \
  '  curl -sS --fail --proto =https -o "$part" "$CLAUDE_URL" || { rm -f "$part"; die' '  curl -sS --fail --proto =https -o "$part" "$CLAUDE_URL" || { die'
arm "dry run downloads" \
  'elif [ $DRY = 1 ]; then
  echo "+ download' 'elif false; then
  echo "+ download'
echo "arms red: $red, arms green: $bad"; [ "$bad" = 0 ]
