#!/bin/bash
# Mutation arms for provision step 5d (the host unit, hearth#51): each breaks one guarantee and must
# make home/controls report a FAIL. cmp-guarded; an anchor not found exactly once is exit 3.
set -u
cd "$(dirname "$0")/.."
F=home/provision
B=$(mktemp); cp -p $F $B; o=$(mktemp)
trap 'cp -p $B $F; cmp -s $B $F || echo "RESTORE FAILED (trap)"; rm -f $B $o' EXIT INT TERM
# Judged by FAIL lines only: controls exits 1 on a SKIP too, and some runners always SKIP one (a
# runner in the docker group skips control 12), which says nothing about step 5d (Ash, #91 N1).
bash home/controls > $o 2>&1
grep -q '^FAIL' $o && { echo "not green unarmed: $(grep '^FAIL' $o | tr '\n' ' ')"; exit 2; }
grep -q '^ok   5d: ' $o || { echo "not green unarmed: no 5d control ran"; exit 2; }
red=0; bad=0
arm() {
  python3 - "$F" "$2" "$3" <<'EOF' || { echo "ANCHOR NOT FOUND: $1"; exit 3; }
import sys; p, old, new = sys.argv[1:]; s = open(p).read()
if s.count(old) != 1: sys.exit(1)
open(p, "w").write(s.replace(old, new))
EOF
  bash home/controls > $o 2>&1
  cp -p $B $F; cmp -s $B $F || { echo "RESTORE FAILED"; exit 2; }
  n=$(grep -c '^FAIL' $o)
  if [ "$n" -gt 0 ]; then echo "ARM $1: RED ($(grep '^FAIL' $o | head -1 | cut -c1-90))"; red=$((red+1))
  else echo "ARM $1: GREEN"; bad=$((bad+1)); fi
}
arm "started without the frontdesk_home gate" \
  'elif sudo -u "$T" -H "$HPY" -I -m hearth.tenantcheck frontdesk_home >/dev/null 2>&1; then' 'elif true; then'
arm "a different unit overwritten" \
  'if [ -e "$UNIT_DST" ] && ! cmp -s "$UNIT_SRC" "$UNIT_DST"; then' 'if false; then'
arm "never started" \
  '  run systemctl enable --now "hearth-host@$T.service"' '  :'
arm "no daemon-reload after installing" \
  'run systemctl daemon-reload; fi' 'fi'
echo "arms red: $red, arms green: $bad"
[ $bad = 0 ]
