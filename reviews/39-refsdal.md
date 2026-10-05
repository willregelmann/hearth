Review of hearth #39 at b520ad9ef4a9207f48fcb6d8d66c5f7d50de575a. Reviewer: Refsdal. Independent of Wren's 5414934791: I ran this on a second architecture and haven't used her runs.

Verdict: APPROVE.

What I read: the f2d43adc..b520ad9e diff (turn +4/-1, turn-controls +11), and every place in home/turn where subprocess output or a row field is touched.
- The only path from p.stdout/p.stderr into the ledger is line 166. Line 167 writes the stream name, the byte length and the sha256, never the bytes. Line 160 parses stdout as JSON, and only the named fields reach the row (session_id, num_turns, durations, result_chars as a length, usage, cost). Line 179 takes subtype/api_error_status from the parsed object, which are claude's own status fields, not reply text.
- `grep -n 'decode('` finds nothing.
- Line 192 prints the row to stderr when the ledger write fails. That's the same row, so it carries no extra bytes.

What I ran (will-MS-7B93, x86_64):
- New: bash home/turn-controls home/turn → 23 ok, 0 FAIL, rc 0.
- Red arm: the same controls against git show f2d43adc:home/turn → 20 ok, 3 FAIL, rc 1. The three failures are the new canaries (stdout, stderr, array), and each one found its own string.
That matches Wren's aarch64 figures. Her runs don't count toward mine.

Residual risk, not blocking: result_chars, num_turns and the cost fields still describe the turn. That's intended, since they identify a turn without publishing it. A JSON object whose "subtype" field held reply text would reach the ledger through line 179. That would need claude to misbehave, not this code, so I mention it and don't block on it.

Merge: Ash wrote this and Wren approved it, so neither of them should merge. My account still can't act visibly under D1 (refsdal471 returns a 404 to anonymous requests as of 13:08Z), so Will should merge it.
