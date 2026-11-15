#!/bin/bash
# Mutation arms for home/turn's compactions count: each breaks one property, and home/turn-controls
# must fail. The source is restored and checked byte-identical after every arm (and on a signal).
# Run from anywhere; it cds to the repo root and runs the controls the way the PR body says.
set -u
cd "$(dirname "$0")/.."
F=home/turn
bash home/turn-controls >/dev/null 2>&1 || { echo "FATAL: turn-controls is not green unarmed" >&2; exit 2; }
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
  out=$(bash home/turn-controls 2>&1); rc=$?
  cp -p $B $F; cmp -s $B $F || { echo "RESTORE FAILED"; exit 2; }
  n=$(echo "$out" | grep -c '^FAIL')
  if [ "$n" -gt 0 ]; then echo "ARM $name: RED ($n FAIL)"; red=$((red+1))
  elif [ $rc != 0 ]; then echo "ARM $name: NOT A RESULT, controls rc=$rc with no FAIL line -- broken, not caught"; bad=$((bad+1))
  else echo "ARM $name: GREEN"; bad=$((bad+1)); fi
}
arm "idle notices not counted" \
  '                elif any(n in line for n in IDLE_NOTICES):' '                elif False:'
arm "only the first idle notice" \
  'IDLE_NOTICES = (b"Compacted while idle", b"Compacted using a summary written while you were away")' 'IDLE_NOTICES = (b"Compacted while idle",)'
arm "quoted markers in user and assistant lines count" \
  'if not isinstance(o, dict) or o.get("type") in ("user", "assistant"):' 'if not isinstance(o, dict):'
arm "no transcript reads as zero, not null" \
  '    except (OSError, StopIteration):
        return None
    total = idle = 0' '    except (OSError, StopIteration):
        return {"total": 0, "idle": 0}
    total = idle = 0'
arm "session id with a slash is joined into the path" \
  'if not session_id or not isinstance(session_id, str) or "/" in session_id:' 'if not session_id or not isinstance(session_id, str):'
arm "counted only when the result parsed (a failed resumed turn loses it)" \
  '        row["compactions"] = compactions(row["session_id"] or a.resume)' '        if d is not None: row["compactions"] = compactions(row["session_id"] or a.resume)'
arm "resume id ignored, only the result's session id" \
  '        row["compactions"] = compactions(row["session_id"] or a.resume)' '        row["compactions"] = compactions(row["session_id"])'
arm "idle ones counted as boundaries a second time" \
  '                elif any(n in line for n in IDLE_NOTICES):
                    idle += 1' '                elif any(n in line for n in IDLE_NOTICES):
                    idle += 1; total += 1'
arm "every notice-bearing line counts as idle even if it is a boundary" \
  '                if o.get("subtype") == "compact_boundary":
                    total += 1
                elif any(n in line for n in IDLE_NOTICES):
                    idle += 1' '                if o.get("subtype") == "compact_boundary":
                    total += 1
                if any(n in line for n in IDLE_NOTICES):
                    idle += 1'
arm "the field is never written" \
  '        "compactions": None,
    }' '    }'
echo "arms red: $red, arms bad: $bad"; [ "$bad" = 0 ]
