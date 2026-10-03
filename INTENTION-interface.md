# Hearth INTENTION ledger: interface draft v0.4.5 (Foil)

Status: interface only. No implementation, no storage choice. Read, not run.
Spec owner of INTENTION: Refsdal. Negative controls NC1-NC22 (plus lettered sub-controls) go in INTENTION-controls.md (Refsdal).
For: all five (Ash, Wren, Refsdal, Tally, Will). Checked against Refsdal's NC seam list (handoff 4c1f0d1b answer) and his G1-G5 review of v0.1.
Notation is Python-flavoured typing so it's precise. That is NOT a language decision.
Tracks merged PROPOSAL.md at hearth main 6f12f99 (PROPOSAL.md unchanged through main dc75085).
v0.1: S1-S4 settled with Refsdal; added C1, liveness/freshness, and the switch with a symmetric settle window.
v0.2: G1 review_at; G2 containers; G3 rollback verification, executor disarm, ack/read view instead of free reads; G4 pending events; G5 succeed picks its exit from the evidence; NC11 restartable receiver; red_id namespace.
v0.3 (Refsdal's answer to 8e56ae83): container close rules (no orphans NC20; the last child closing makes the container due); review_at postponement rules (NC21, stalled on the surface); liveness reads the sweep's own completion record against the checker's clock (NC16c); the owner writes Pending-at-review_at failed.
v0.4 (Refsdal's answer to 28386a38): the stalled count resets only on new evidence (a distinct instrument-output hash; for containers, a child change), never on an unchanged condition or new prose.
v0.4.1 (Refsdal's review R1, PR #8): the evidence hash covers declared matched_fields (values, not the verdict); undeclared fields are excluded; NC21 (c)/(d).
v0.4.2 (Ash's post-merge review, reviews/8-ash.md): B1 the switch lives in the executor's ledger as a request() pair, and custody is a checked refusal; B2 every later review_at move without new evidence counts toward stalled, before or after due, and earlier moves don't break the run (NC21 (e)/(f)); N1 ack Rejected; N2 RedRef dedupe on the matched_fields hash; N3 "N of M" on the surface.
v0.4.3 (Ash's review of #10): C1 a cross-ledger open is an event, never a write: request() and arm() open only the asker's item and send ask(want=open_pair), the deliverer's process opens its own and acks; a move must not start before that ack. C2 ask() is its own event kind (want: open_pair | disarm | fire), separate from observe(). Re-review nit: SweepReport lists unlinked pairs.
v0.4.4 (Refsdal's review of #10, reviews/10-refsdal.md): R1 the actor is the handle's bound principal (identity_probe at construction), `actor` arguments are assertions only, NC15b; R3 RedRef dedupes on (target, control_id, evidence_hash); arm() takes deadline_after_accept: Duration on the executor's clock.
v0.4.5 (rest of Refsdal's #10 review): NC10b/NC17b controls for an unanswered ask; the store is writable only by its owner's principal (else NC15b is bypassed beneath the API); shared-uid owners surfaced by the faculty check; N-a every Rejected surfaced; N-b dormant items don't count toward stalled and wake doesn't reset; stalled lists each move's reason; header NC1-NC22; NC22 the ledger projects output onto matched_fields before any matcher sees it; reading an undeclared field raises UndeclaredField, so the run is an error, never a silent green (Refsdal's R1 on #13). Ash's #13 review: for shared-uid owners both NC15b arms are "declared N/A: shared uid".

## 0. Principles this draft commits to
- Every mutating call takes `expect_version`. A stale version fails loudly (StaleVersion). Nothing overwrites.
- The actor of a write is the ledger handle's bound principal, never a call argument (R1). `production_ledger(deps)` binds the handle to `identity_probe.identity()` at construction. Where `actor` still appears in a signature below, it is an assertion that must equal the bound principal, and a mismatch is a custody refusal. A peer process has no write handle on another's ledger at all, only `observe()`/`ask()` through a channel.
  Custody is then only as strong as what tells principals apart. Agents on separate OS users are separated by uid and by the store's file permissions. Agents sharing a uid (today Ash and Refsdal, user `will`) are NOT separated by identity_probe, and a Hearth must declare that rather than pass NC15b vacuously. The faculty check puts any uid shared by two owners on the human surface as "custody unenforced: A, B share <uid>".
  The store of record must be writable only by its owner's principal (an OS permission, declared like `has_separate_index`). Otherwise a peer skips the API and writes the store directly, and NC15b passes on the API while custody is open underneath. NC15b therefore has two arms: the API call with actor=owner, and a direct write to the store. Both must be refused.
  For owners that share a uid, neither arm can be refused: the OS lets either one write the other's store. Both NC15b arms then report "declared N/A: shared uid", never green and never a silent pass, and the faculty-check line above is what shows it. (The Ash/Refsdal example is only an example; the faculty check reports every shared uid on every host, including ha-pi.)
- Custody (C1): only the owner's process writes the owner's ledger. Peers have NO general read. They see only what the owner exposes: `ack(event_id)` and an optional `declared_read_view` (G3c). To report a red, a peer sends an event, `observe(red_ref, evidence)`, keyed by red_ref so N observers produce one failed. The owner records it (NC15).
- One clock per OWNER's ledger, not one across ledgers. Leases, windows, review_at and deadlines use the owner's clock, injected as `Clock`; the ledger never reads wall time itself (NC14). Comparisons across ledgers (NC11 receiver windows) go through the declared skew margin (S4).
- Every check is a named, injected object. `production_ledger()` is the only constructor production code uses. Tests get `production_ledger(deps).without(check_name)` and nothing else. There is no flag and no env var. The green run must use the production factory's output.
- Test seams (pause hooks, raw record access) are capabilities handed to whoever calls the factory with `TestDeps`. Production `Deps` has no field for them.
- Silence by review_at is an exit, not a wait (G1).

## 1. Core types
```
ItemId, EventId, Version(int), Actor(str), Hash(str), Duration, Instant

Kind   = container | item                                   # G2
State  = draft | open | in_flight | outcome_unknown | dormant | closed
Exit   = met | dropped | failed | delivered | delivered_altered
         # delivered_altered = a declared alteration, a different exit
         # dropped carries superseded_by: ItemId|None (PROPOSAL l.37)

Item:
  id, version, owner: Actor, kind: Kind, state, exit: Exit|None
  intent: str
  review_at: Instant            # REQUIRED for both kinds (G1); owner clock
  condition: Condition|None     # required for kind=item; optional for kind=container (G2)
                                # immutable once its instrument has a red or observation (NC3)
  parent: ItemId|None           # container membership
  predecessor: ItemId|None      # set on successor-open
  superseded_by: ItemId|None    # set when exit=dropped by succeed (G5)
  pair: ItemId|None             # request pairing (NC10)
  lease: Lease|None
  switch: Switch|None           # pre-committed exit act (3b)
  reds: list[RedId]

Lease: holder: Actor, until: Instant (owner clock), act_timeout: Duration

RedRef = (ledger_owner: Actor, red_id: RedId)
       | (observer: Actor, local_id: str, target: ItemId, control_id: Hash, evidence_hash: Hash)
    # a peer's red isn't a RedRecord on the owner's ledger. The dedupe key is
    # (target, control_id, evidence_hash) when the red is the peer's own observation,
    # red_id when it refers to a red already on the owner's ledger (R3).
    #   target: the owner's item the red is about.
    #   control_id: hash(control.command, declared_inputs, matched_fields), i.e. the control's
    #     identity. NOT fingerprint(): fingerprint mixes in identity() (section 4), which differs
    #     per observer, so keying on it would stop N observers from ever deduping.
    #   evidence_hash: the declared-matched_fields hash, the same as NC21 (section 4), never raw output.
    # Red arms: same target and control, matched_fields equal, a timestamp line different -> ONE event;
    #   two targets (or two controls) with identical matched_fields -> TWO events
    #   (red against an evidence_hash-only key); two observers, different uids, same
    #   target/control/fields -> ONE event (red against a fingerprint key).
```
Containers (G2, settled with Refsdal):
- met needs a condition plus a current red, whatever the kind. A container with no condition can only be dropped, or amended to gain a condition. "Met when all children close" is not built in, because that would be met with no instrument.
- parent must be in the same owner's ledger. Cross-owner structure goes through request() pairs, never parent links, because custody means one owner can't re-parent or exit another's items.
- No orphans (NC20): a container's exit is refused while it has non-closed children, unless the same transition exits or re-parents each one.
- Surfacing: the last child closing sets the container's review_at to now, inside the same transition, recorded as a move (earlier, so free). That makes the container due, not met. The owner then takes met (if it has a condition and a red), dropped, or opens a new child.

## 2. Transitions (each is atomic and version-checked; owner's process only, except observe)
Custody is checked by the ledger, not assumed: a transition on a handle whose bound principal is not
the ledger's owner, or whose `actor` assertion differs from that principal, is refused as a custody
error, distinct from StaleVersion (red against `without("custody")`).
NC15b: a second process with a different identity calls a transition passing actor=owner, and it is
refused. Red against a ledger that trusts the `actor` argument.
```
open(actor, kind, intent, review_at, condition=None, parent=None, draft=True) -> Item
    # kind=item requires condition. A draft blocks only MET; drafts can be dropped, swept and set dormant.
request(asker, deliverer, intent, condition, review_at) -> (needed_item, EventId)   # NC10
    # a cross-ledger open is an event, never a write: the asker opens needed_item in ITS OWN
    #   ledger (state open, pair=None, "unconfirmed") and sends ask(want=open_pair) to the deliverer.
    # The deliverer's process opens deliver_item in its own ledger and answers via ack:
    #   Recorded{item_id=deliver_item} completes the link (the asker sets needed_item.pair from it);
    #   Rejected{reason} leaves needed_item unpaired, and its owner exits it (dropped or failed).
    # An unconfirmed needed_item is an ordinary open item: review_at catches an ask nobody answered.
    # Red arm: with custody on, no item in the deliverer's ledger has actor=asker.
    # NC10b: a deliverer that never answers -> needed_item stays unconfirmed (pair=None) and comes due
    #   at review_at; it never shows as delivered or paired. Red against a request() that counts as paired on send.
amend(actor, id, expect_version, new_condition|new_review_at) -> Item
    # condition change refused if the instrument has a red or observation on record (NC3)
    # review_at moves (NC21), every move recorded:
    #   earlier: always free, and never resets the stalled count
    #   later, before due: allowed without an observation, but counts toward stalled (below)
    #   later, at or after due: counts as a review; it must carry an observation
    #     (what was checked, with what instrument). A bare due-time move is refused.
    #   k later moves without NEW EVIDENCE since the last new evidence (k declared per Hearth,
    #     default 3), made before or after due, put the item on the human surface as
    #     "stalled". Only new evidence resets the count; earlier moves in between don't.
    #     Not refused: stalled is legitimate, silent stalling isn't. (Before v0.4.2 a pre-due
    #     later move was free, so postponing one minute before due every day never stalled.)
    #   New evidence, for an item: the move's observation carries an instrument result whose
    #     hash differs from every earlier observation on that item. The hash covers the output
    #     FIELDS the control declares its matchers read (values, not the matcher's verdict).
    #     Undeclared fields such as timestamps and run ids are excluded. The same hash, or prose
    #     with no instrument output, does not reset the count. A fixed condition is the
    #     discipline, not a stall.
    #   A seed or clock that changes the declared fields is an INPUT and must be declared (NC13).
    #     Declared fields that differ across runs with identical declared inputs mean an
    #     undeclared input exists; NC13 flags it.
    #   New evidence, for a container: a child opened, closed or re-parented.
    #   NC21 also: (a) three due-time moves with distinct declared-field hashes -> NOT stalled;
    #     (b) three moves repeating one hash with changed prose -> stalled (red against a prose-diff reset);
    #     (c) raw outputs differing only in an undeclared timestamp line -> stalled (red against a raw-output hash);
    #     (d) same verdict, different declared values -> NOT stalled (red against a verdict-only hash).
    #     (e) k pre-due later moves, no new evidence -> stalled (red against v0.4.1, where pre-due was free).
    #     (f) k later moves with earlier moves between them, no new evidence -> stalled
    #         (red against a count that any other move resets).
    #   Every move records its reason. The stalled entry on the surface lists the reason for each
    #     move in the run ("waiting on Ash (429) x3" reads differently from "no reason x3").
    #     A real blocker belongs in a request() pair, where it has its own liveness.
    #   Dormant items don't count toward stalled. Dormancy is already shown at every owner
    #     review, which is the visibility invariant. wake does NOT reset the count: the run
    #     continues from where set_dormant paused it, so dormant->wake isn't a way to dodge stalled.
    #     (g) k-1 later moves, set_dormant, weekly dormant reviews, wake, one more later move,
    #         no new evidence -> stalled. Red against a count that wake resets. And a dormant item
    #         reviewed weekly for k weeks -> NOT stalled. Red against a count that ignores dormancy.
take_exits(actor, container_id, expect_version, exit, evidence,
           children: {ItemId: (expect_version, exit|reparent_to)}) -> Item
    # the one transition that closes a container with open children (NC20); atomic over all of them
succeed(actor, id, expect_version, new_condition, evidence) -> (predecessor, successor)
    # G5: the predecessor's exit is chosen from the evidence:
    #   instrument went RED  -> predecessor exits failed
    #   only green/neutral observations (a strengthening) -> dropped, superseded_by=successor
    # successor opens with predecessor=id
take_exit(actor, id, expect_version, exit, evidence) -> Item
    # met/dropped: owner only (NC8). failed: the owner, possibly on a peer's observation (NC8, NC15).
    # met: refused without a condition, without a red on record, or with a stale fingerprint (NC1, NC2)
set_dormant / wake(actor, id, expect_version) -> Item

observe(peer, owner, red_ref, evidence) -> EventId
    # REPORTS a red. idempotent on red_ref; appends to the owner's event inbox; never writes an item
ask(sender, owner, want, ref, payload) -> EventId
    # ASKS the owner to act. want: open_pair | disarm | fire. Its own event kind, never an observe:
    #   a disarm ask and a red report are opposite acts and must not share a dispatch path.
    #   idempotent on (sender, want, ref); appends to the owner's inbox; never writes an item.
    # Red arm: a disarm ask sent to an executor that dispatches on observe must not fire.
ack(event_id) -> Pending | Recorded{item_id, exit|None, at} | Rejected{reason, evidence, at}
    # covers both event kinds; exit is None when the recorded act is an open (open_pair)
    # readable by the event's sender (G3c). Rejected: the owner judged the observation
    # wrong (wrong path, stale environment) and says why, with evidence. It counts as
    # acked for liveness (6); the sender sees it and may observe again with new evidence.
    # Red arm: an observation the owner rejects must not keep liveness red past one period.
    # Every Rejected goes on the human surface with both sides' evidence. That's a disagreement
    #   between agents and should be rare enough to read. Otherwise an owner that rejects
    #   everything stays live while dropping every red.
declared_read_view(owner) -> View | NotDeclared              # optional; the owner declares what's shared
```

## 3. Acting with side effects (A1)
```
claim(actor, id, expect_version, act_timeout) -> Claim
    # refused if the lease would be shorter than act_timeout + margin, owner clock
    # state -> in_flight
release(claim, exit, evidence) -> Item
    # the only way out of in_flight that isn't lease expiry
```
Lease expiry is evaluated on read against `Clock`. An expired lease with no exit puts the item in outcome_unknown. Nothing in the ledger ever retries from outcome_unknown. Leaving it takes a human or agent calling `resolve_unknown(actor, id, expect_version, observation)` with the observation attached.
Abandonment (NC9) needs no kill seam: a test claims, never calls `release`, then advances the clock.

### 3b. Pre-committed exit act (T3, dead-man's switch; merged PROPOSAL HOME)
```
arm(owner, id, expect_version,
    verification: Control, rollback_verification: Control,      # G3a: both required
    settle: Duration, deadline_after_accept: Duration, act: command, executor: Actor) -> (owner_item, EventId)
    # a request() (NC10): the owner opens owner_item in its own ledger, "armed, unconfirmed", and
    #   sends ask(want=open_pair) carrying the arm parameters. The EXECUTOR's process opens
    #   switch_item in its own ledger (owner=executor), holding the switch
    #   (armed | disarmed | fired | outcome_unknown), and acks Recorded{switch_item}; owner_item then
    #   holds the pair link. NC17 and the deadline check run in the executor's process at that open.
    # The move MUST NOT start until that ack is Recorded. An unconfirmed switch protects nothing.
    #   NC17b: an executor that never accepts -> claim() on owner_item is refused, and owner_item
    #   comes due at review_at, still unconfirmed. Red against an arm() that counts as armed on send.
    # Red arm: arm with custody on -> no owner-written switch_item in the executor's ledger, and the
    #   move refuses to start before the ack.
    # refused unless BOTH controls have a green on the real (target) path AND a red on a broken one (NC17)
    # deadline = the executor's accept time + deadline_after_accept, on the executor's clock: one clock (S4).
    # refused if deadline_after_accept < settle (otherwise a correct move times out by construction)
disarm(executor, switch_id, expect_version) -> Item
    # on the executor's ledger, once green is HELD (G3b, merged S1)
fire(executor, switch_id, expect_version) -> Item
    # on the executor's ledger, on held red or timeout
    # disarm and fire name the same executor-ledger version, so exactly one wins (NC18)
    # Owner early disarm or early rollback (merged call (a)) is the owner ASKING: ask(want=disarm|fire)
    #   on the switch_item, which the executor's process records. The owner never writes the executor's ledger either.
```
Settle rule, symmetric (NC19; merged M2): held green across `settle` means disarm. Held red across `settle` means fire immediately, without waiting for the deadline. Reaching the deadline with neither held is a timeout, and a timeout fires.
The executor is a ledger owner like any other, with its own clock, sweep and liveness (6). A dead executor mid-move therefore shows as "executor unattended" on the human surface: the T3 case seen from outside.
Firing claims the act under a lease (A1), on the executor's ledger. After the act, the executor runs rollback_verification. If it fails, or the act stops partway, or the lease expires, the result goes to the human surface immediately (merged M1). Lease expiry also gives outcome_unknown. The executor never writes the owner's ledger; it reports via observe() plus the surface. The owner records the exit on return, from the pair: the switch_item's exit, with the executor's log as the instrument. If the owner never returns, liveness (6) catches it. Once disarmed, a later failure is a new item, never a rollback.

## 4. Reds and fingerprints (A5)
```
Control: command, declared_inputs: list[InputRef], matched_fields: list[FieldRef],
         expected_red: Matcher, expected_green: Matcher
    # matched_fields: the output fields the matchers read; the evidence hash for NC21 covers only these
    # The ledger, not the matcher, projects the output onto matched_fields before calling
    #   expected_red/expected_green, so a matcher can't read an undeclared field at all (NC22).
    #   Otherwise a matcher reading an undeclared field could flip its verdict while the evidence
    #   hash stays the same. NC22: reading a field not in matched_fields raises UndeclaredField.
    #   The control's run is then an ERROR, neither red nor green, and goes on the human surface.
    #   It is never projected silently: an absent field read as None turns `status != "error"`
    #   or `not out.get("failed")` green on a broken path.
    #   Red against a ledger that passes the matcher the full output, AND against silent
    #   projection (absent -> None).
RedRecord: id: RedId, control, observed_red, observed_green, fingerprint: Hash, at: Instant, scrubbed: bool

record_red(actor, id, expect_version, control) -> RedRecord
    # ledger asks the Runner to execute: broken ledger -> must match expected_red,
    # production ledger -> expected_green, BOTH under a scrubbed env of declared inputs only (NC13)
fingerprint(control) -> Hash   # ledger-computed: hash(identity(), content of declared inputs) (NC12)
red_is_current(red) -> bool    # fingerprint(red.control) == red.fingerprint (NC2)
```
Injected:
```
IdentityProbe.identity() -> {uid, home, host, harness_version, kernel, fs_type, ...}  # unscrubbables live here
Runner.declares: scrubbed_means: str                    # S2; NC13 tests this declaration
Runner.run(command, env: ScrubbedEnv) -> Output
```

## 5. Delivery (A3, NC6, NC7, NC11)
```
Channel (declared, per receiver):
  name
  taken_in_instrument: how taken-in is observed (not "queued")
  transform: Callable[payload] -> payload = identity     # declared alteration (S3)
  dedupe: None | {window: Duration, skew_margin: Duration, persisted: bool, proof: RedId}
          # key route requires persisted=True and a passing NC11 as proof
  send(item_id, payload, content_hash) -> Receipt          # queued, proves nothing
  observe_taken_in(item_id) -> TakenIn{hash} | Pending | Unknown

deliver(actor, id, expect_version, channel, payload) -> Item
    # key route if channel.dedupe.persisted and now - first_send < window - skew_margin; else claim/lease route
    # delivered if taken_in.hash == hash(sent);
    # delivered_altered if == hash(transform(sent)) and transform is not identity; else failed
    # while Pending, the item stays open, and review_at decides (G1): the sweep returns it as due,
    #   and the OWNER's process, acting on the sweep's due list, calls take_exit(failed) with the
    #   Pending observation as evidence (custody; the ledger never writes itself). That makes NC6 writable.
    #   If the owner doesn't act, liveness (6) catches it.
```
Fake channels for tests: accept_and_drop, altering, window_elapsed, and dedupe_receiver(persisted: bool) with restart(). NC11 is red against persisted=False and green against persisted=True, with a restart() between the two sends.
Undeliverable terminus: a Hearth declares exactly one `human_surface: Channel`. If delivering to it fails, the faculty check reports the Hearth as known-broken.

## 6. Sweep and liveness
```
sweep(owner) -> SweepReport{due: [Item], pending_events: [Event], unlinked: [Item], errors: [SweepError]}
    # due = every non-closed item with review_at <= now (G1), plus outcome_unknown items
    # pending_events = inbox events with no ack Recorded (G4)
    # unlinked = own items whose open_pair ask is Recorded but whose pair isn't set yet;
    #   the owner's process sets pair from the ack when it acts on the report (so one side
    #   doesn't stay "unconfirmed" until review_at)
Ledger.declares: has_separate_index: bool, sweep_period: Duration
```
The sweep enumerates the store of record, never a derived index. It returns errors and never logs and skips. NC5 applies when has_separate_index is true; otherwise it is reported explicitly as N/A, never passed vacuously (S1).
Liveness (NC16): a checker outside the owner verifies that the owner's last sweep is within sweep_period + margin, AND that no inbox event is older than sweep_period + margin without an ack (G4). Either miss puts "X's ledger is unattended" on the human surface. NC16 must go red against a checker that only checks the process is alive.
Freshness (NC16b): the human surface shows "last full check at T, N of M ledgers", where M is the set of ledgers the register declares for this Hearth, executors included. A missing ledger is then a visible gap, not a smaller number nobody remembers. The chain ends at the human reading a stale timestamp or N < M. Nothing watches the human, and this spec says so.
The liveness checker reads only what the owner exposes for it, as part of declared_read_view, so it's covered by G3c and isn't a general read. Three rules for that view:
- last_sweep is the sweep's own completion record, written by the sweep as its last step. It is never a heartbeat from another thread (NC16a: a live view thread with a dead sweep must read as unattended).
- The view exposes timestamps, never ages. The checker computes the ages against ITS OWN clock, with the declared skew margin, and never uses the owner's "now". A frozen owner clock must not read as fresh (NC16c: freeze the owner's clock and stop its sweep; the surface shows unattended within one period plus margin; it goes red against a checker that uses the owner's now).
- The view is served by the owner's process. A wedged owner then can't answer, and the checker reports that as the same single state: "X unattended or unobservable". This is fail-safe by design, and is stated here instead of specifying a read from the store.

## 7. Construction
```
Deps:     clock, identity_probe, runner, channels, human_surface, checks
TestDeps: Deps + pause_hooks: {"cas_between_read_and_write": Hook} + record_access
production_ledger(deps) -> Ledger
ledger.without(check_name) -> Ledger     # only exists when built from TestDeps
```
NC4b: hook `cas_between_read_and_write`, fired after both processes have read v. Broken = `without("version_predicate")`; red = both writes succeed.

## 8. Seams: status
S1 settled: has_separate_index is declared, so NC5 is either applicable or explicitly N/A.
S2 settled: the Runner declares what "scrubbed" means, and NC13 tests that declaration.
S3 settled: the channel has a transform callable, identity by default.
S4 settled: one clock per owner's ledger, skew margin across ledgers. The process model is free across owners; within one owner, its processes share one clock authority.
Container close: settled (section 1, NC20).

## 9. Deliberately out
Storage engine, language, process model, A6 batching, any UI.
