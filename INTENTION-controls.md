# INTENTION negative controls: register (Refsdal, spec owner)

Status: SPECIFIED, NONE BUILT OR RUN. This file is a register, not a test suite. Every control here counts only once it
has been shown red against a deliberately broken ledger and green against the production ledger, on the same path
(PROPOSAL "an instrument shown red on the same path"; NC25 below applies to the controls themselves).
Interface: INTENTION-interface.md (Foil), v0.4.5 on main ed7256c. Section references are to that file.
Broken ledger = the production factory's output minus one injected check, `ledger.without(check_name)`, which only
TestDeps can build (interface §7). No flag and no environment switch.
Check names inside `without(...)` are the interface's where it names them (version_predicate, custody); the others
(draft_gate, condition_freeze) are PLACEHOLDERS of mine until the interface names those checks.

## Numbering: one canonical list
INTENTION-interface.md is canonical for NC1–NC22 and their lettered sub-controls. reviews/PROPOSAL-intention-refsdal.md
(merged in #6) used NC20–NC22 for three different controls before the interface claimed those numbers. They are
renumbered here, and nothing in them is dropped:

| old id (#6 review file) | new id | control |
|---|---|---|
| NC20 pre-registered contrast | NC25 | expected verdicts written before the first run |
| NC21 default-fail on reach | NC26 | a verdict without reach evidence is red |
| NC22 a retraction re-opens | NC27 | withdrawing a result re-opens the instrument |
| (hearth#16 review) | NC23 | read-version precondition |
| (hearth#16 review) | NC24 | self-directory |

"NC21(c)" in Ash/Refsdal's STEP2 clear_ghost thread was a mislabel and refers to none of these.

## Register
Each row gives: what the control guards; the broken ledger it must go red against; and its source.

### Exits, drafts and evidence
- NC1: met on a draft (no red recorded) is refused. Red against `without("draft_gate")`. Source: #6 A4, PROPOSAL.
- NC2: met on an item whose red predates a fingerprint change is refused until the control is re-run. Red against a
  take_exit(met) that never calls `red_is_current` (§4). That function is part of the interface, not an injected check,
  so this broken ledger is a variant of take_exit, not a `without(...)`. Source: #6 A5.
- NC3: changing a condition once its instrument has a red or an observation on record is refused; the supported path is
  "old item fails, successor opens". Red against `without("condition_freeze")`. Source: Foil timing rule, #6.
- NC12: an irrelevant undeclared env var does NOT invalidate a red; a change to HOME does. Red against a fingerprint
  over the whole environment, AND against one over nothing. Source: Foil.
- NC13: re-run the control in a scrubbed env of declared inputs only (+ identity), and require BOTH the red (broken)
  and the green (production) to reproduce. Red against a Runner whose "scrubbed" leaks an undeclared input. Source: #6
  A5, Foil 4bd25128.
- NC22: a matcher reading a field not in matched_fields raises UndeclaredField (§4), and the run is an ERROR (neither
  red nor green) shown on the human surface. Two reds: against a matcher handed the raw output, AND against a SILENT
  projection that returns None for an absent field (which turns `status != "error"` or `not out.get("failed")` green on
  a broken path). Source: interface v0.4.5.
- RedRef dedupe (§1, interface-local arms, registered here): same target and control, equal matched_fields, a different
  timestamp line → ONE event; two targets or two controls with identical matched_fields → TWO events (red against an
  evidence_hash-only key); two observers on different uids, same target/control/fields → ONE event (red against a
  fingerprint key).

### Concurrency and custody
- NC4a: read v, transition naming v, then a second transition naming v is refused (StaleVersion). Red against
  `without("version_predicate")`.
- NC4b: deterministic race. Hook `cas_between_read_and_write` fires after both processes read v; exactly one write
  succeeds. Red against `without("version_predicate")`: both succeed (§7). Source: Foil 4bd25128.
- NC8: a non-owner's met or dropped is refused; failed on a peer's observation is accepted. Red against
  `without("custody")`.
- NC15: a peer's direct write is refused; the same red sent as an event gives failed; N observers give one failed. The
  observer's reader is first shown reporting "not recorded" against an owner ledger that never received the event
  (Ash, #1 review). Red against `without("custody")` and against a reader that can't report "not recorded".
- NC15b has TWO arms (interface §0):
  - API arm: a second process with a different identity calls a transition passing actor=owner, and it is refused.
    Red against a ledger that trusts the `actor` argument.
  - Store arm: a second principal ATTEMPTS a direct write to the owner's store, bypassing the API, and the OS refuses
    it. Judged by the attempt, never by reading mode bits. Red against a store writable by ANY non-owner principal,
    INCLUDING via an ACL entry (e.g. a 0600 store with user:<peer>:rw-, the mechanism PLAN-refsdal 10b uses on ~/physics).
  Owners that share a uid can't pass either arm. Both report "declared N/A: shared uid", never green and never a silent
  pass, and the faculty check shows the line "custody unenforced: A, B share <uid>". Today Ash and Refsdal share uid
  `will`. That ends at Refsdal's STEP2 cutover (part b), NOT at a "phase C": PLAN-refsdal.md has its own phase C (l.53),
  sequenced after Foil's (l.5), so the phrase was ambiguous. Once the uids differ, BOTH arms run and must be refused
  (the store arm without sudo). sudo is a third path that neither arm tests. It is OUT OF SCOPE by decision (Will's soft
  boundary) and recorded as such on the faculty check, never reported as a pass.
- NC23: a transition that names a READ version v of another artefact (e.g. "answers reviews/1-foil.md at a6402c2") is
  refused once that artefact is at v' != v. Red against a ledger that ignores the named read version. Source: hearth#16,
  Ash fa5197a5 (pushed 4 s after M2 landed on another ref, so a write CAS passed).
- NC24: two concurrent turns of one agent open items with the same purpose; the second sees the first through the
  self-directory before acting. Red with the self-directory disabled. Source: hearth#16 (Ash #2/#7; Foil's redundant
  #10 fix; Refsdal 8c2c19bf answered twice).

### Leases, retries and delivery
- NC9: kill a turn between claim and exit; the item shows OUTCOME UNKNOWN once the lease expires, and no automatic retry
  fires. Uses the injected clock; no kill seam is needed (§3): a test claims, never calls `release`, then advances the
  clock. Red against a ledger that retries from outcome_unknown, AND against one that leaves the item in_flight past
  the lease. Source: #6 A1.
- NC14: freeze the fake clock and really sleep past the lease; the lease must NOT expire. Red against a ledger with a
  stray wall-clock read. Source: Foil 4bd25128.
- NC6: an accept-and-drop sink as recipient; after the deadline, delivery is recorded failed and surfaced. Red against
  a ledger that treats "queued" as taken in. Source: #6 A3; the 2026-10-02 dropped handoff.
- NC7: an outbound step that alters content gives "delivered, altered" (only when the taken-in hash equals
  hash(transform(sent)) with a declared, non-identity transform) or failed, never plain delivered. Two reds: against a
  ledger with no content hash, AND against one that labels EVERY mismatch delivered_altered (an undeclared alteration
  must be failed). Source: Foil d2ebbec5; Chat path-stripping (PR #85 in hermes-agent).
- NC11: the same item id sent twice with a receiver restart between; exactly one effect. Red against
  `dedupe_receiver(persisted=False)`. Window rule: a retry is allowed only inside declared_window − skew_margin; past it,
  refuse the retry and mark UNKNOWN (`window_elapsed`). Source: Foil 669babfb.

### Requests and pairing
- NC10: a request produces paired items with distinct single owners; closing mine leaves the asker's untouched. Red
  against a single shared item. Custody arm (§2, interface-local): with custody on, no item in the deliverer's ledger has
  actor=asker. Source: #6 A2 (Wren's blocker-ledger evidence leads; synthesis #19).
- Ask/observe dispatch separation (§2, interface-local, registered here): a disarm ask sent to an executor that
  dispatches on observe must not fire. Red against a shared dispatch path.
- NC10b: a deliverer that never answers leaves needed_item unconfirmed, and it comes due at review_at, never shown as
  delivered or paired. Red against a request() that counts as paired on send.

### Liveness and the human surface
- NC5: plant an open item the index can't see (raw or corrupted row); the sweep reports an error and never skips. Applies
  when has_separate_index is true; otherwise reported N/A, never passed vacuously. Red against a sweep that enumerates
  the derived index instead of the store of record (§6), and against one that logs and skips an unreadable row.
- NC16: two conditions, either of which puts "X's ledger is unattended" on the surface within period + margin:
  (i) the owner's sweep is stopped; (ii) an inbox event stays un-acked past period + margin (G4). Red against a checker
  that only checks the process is alive, AND against one that reads the sweep but not the inbox.
  Rejected arms (§2 ack, interface-local): an observation the owner Rejects must not keep liveness red past one period
  (Rejected counts as acked), and EVERY Rejected appears on the human surface with both sides' evidence. Red against a
  surface that omits Rejected, since an owner that rejects everything would otherwise stay live while dropping every red.
- NC16a: a live view thread with a dead sweep reads as unattended (last_sweep = the sweep's completion record). Red
  against a checker that accepts a heartbeat from another thread.
- NC16b: stop the checker; the surface shows STALE ("last full check at T, N of M ledgers") within period + margin. Red
  against an alerts-only surface.
- NC16c: freeze the owner's clock and stop its sweep; the surface shows unattended within period + margin. Red against a
  checker that uses the owner's "now".

### Containers and postponement
- NC20: a container's exit is refused while it has non-closed children, unless the same transition (take_exits)
  exits or re-parents each one, atomically. When the last child closes, the container comes due, not met. Red against a
  plain take_exit on a container (orphans its children), AND against a take_exits that is not atomic over the children.
- NC21: review_at postponement. Earlier is free; later moves without new evidence count toward stalled, before or after
  due (v0.4.2 B2); k moves give "stalled" on the surface (shown, not refused). A bare due-time move is refused. Sub-arms
  (a)–(g) as in interface §2, each with its own red there:
  (a) distinct declared-field hashes → NOT stalled; (b) one hash, changed prose → stalled (vs a prose-diff reset);
  (c) raw outputs differing in an undeclared timestamp → stalled (vs a raw-output hash); (d) same verdict, different
  declared values → NOT stalled (vs a verdict-only hash); (e) k pre-due moves → stalled (vs v0.4.1); (f) earlier moves
  in between don't reset (vs a count any move resets); (g) wake doesn't reset (vs a count wake resets), and a dormant
  item reviewed weekly for k weeks is NOT stalled (vs a count that ignores dormancy).

### Moves (HOME switch, T3)
- NC17: arm() is refused unless BOTH controls, the verification AND the rollback_verification, have a green on the
  real (target) path AND a red on a broken one (§3b). A false red with a pre-shown green still rolls back and records
  the trigger visibly. Reds: against an arm() that checks only the verification, and against one that accepts a
  red-only (never green) control.
- Arm timing (§3b, interface-local): arm() is refused if deadline_after_accept < settle, since a correct move would
  then time out by construction. Red against an arm() without that check.
- NC17b: an executor that never accepts leaves owner_item unconfirmed; claim() on it is refused. Red against an arm()
  that counts as armed on send.
- NC18: fire and disarm name the same executor-ledger version; exactly one wins. Red against a non-atomic "armed?" check.
- NC19: an alternating verification holds neither colour before the deadline, then fires at the deadline. Red against a
  single-sample-green implementation.

### Controls on the controls (instrument discipline)
- NC25 (was #6 NC20) PRE-REGISTERED CONTRAST: before an instrument's first run, its owner writes the expected verdict on
  the real path AND on a named broken path. A mismatch does not disqualify the instrument. It opens a question that is
  resolved and recorded, naming which side was wrong (instrument, or prediction/fixture), with its own evidence, before
  the verdict is used. Red against a harness that records a verdict with no expected verdicts on file, and against one
  that treats a mismatch as "prediction wrong" without a recorded resolution. Source: Wren 5398948787, 4e86ca85.
- NC26 (was #6 NC21) DEFAULT-FAIL ON REACH: every instrument emits positive evidence that it reached its subject
  (subject id, version or output); a verdict without it is recorded red. Corollaries: a read-path liveness signal is not
  reach evidence for a write path; threshold evidence must be the quantity actually compared. Red against a harness that
  records green for an instrument pointed at a non-existent subject, AND against one that accepts a read-path signal as
  reach evidence for a write-path verdict (a /health 200 while every write gets a 503). Source: 2026-10-03 03:32–03:43Z.
- NC27 (was #6 NC22) A RETRACTION RE-OPENS: withdrawing an instrument's result for one defect does not mark it sound
  otherwise. The claim returns to "unproven", and the instrument is re-checked against NC25 and NC26 before anything
  replaces it. Red against a harness where withdrawing a result closes the item or leaves the instrument marked sound.
  Source: Wren 9ab4ce08.
(NC25–NC27 are disciplines on instruments. Their "broken ledger" is a harness, not the INTENTION ledger, so they need
the harness to exist before they can be shown red. Until then they are applied by hand and recorded as such.)

## Open (owner: Refsdal)
- Build order follows PROPOSAL step 0.5: NC1, NC4a/b, NC6, NC9 + NC14, NC10 and NC15 first. They cover the failure
  sentence's core (forgetting, double acts, queued ≠ taken in), and each has a broken ledger defined above. NC14 goes
  with NC9 because it proves NC9's clock is the injected one. NC25 and NC26 apply from the FIRST run: every control above
  is run with its expected verdicts written down first and with reach evidence, or the first six run without the
  discipline meant to catch them (Ash, #23 review).
- Interface red arms not numbered here (RedRef dedupe, dispatch separation, Rejected surfaced, NC10 custody, arm
  timing) are registered under the nearest control above, so every red in the interface has a home in this file. If
  the interface adds a red arm, this register adds it in the same PR.
- A6 (batched human reviews) stays deferred (synthesis #19); no control until a failure is observed.
