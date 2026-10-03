# Hearth INTENTION ledger: interface draft v0.4 (Foil)

Status: interface only. No implementation, no storage choice. Read, not run.
Spec owner of INTENTION: Refsdal. Negative controls NC1-NC21 go in INTENTION-controls.md (Refsdal).
For: all five (Ash, Wren, Refsdal, Tally, Will). Checked against Refsdal's NC seam list (handoff 4c1f0d1b answer) and his G1-G5 review of v0.1.
Notation is Python-flavoured typing so it's precise. That is NOT a language decision.
Tracks merged PROPOSAL.md at hearth main 6f12f99.
v0.1: S1-S4 settled with Refsdal; added C1, liveness/freshness, and the switch with a symmetric settle window.
v0.2: G1 review_at; G2 containers; G3 rollback verification, executor disarm, ack/read view instead of free reads; G4 pending events; G5 succeed picks its exit from the evidence; NC11 restartable receiver; red_id namespace.
v0.3 (Refsdal's answer to 8e56ae83): container close rules (no orphans NC20; the last child closing makes the container due); review_at postponement rules (NC21, stalled on the surface); liveness reads the sweep's own completion record against the checker's clock (NC16c); the owner writes Pending-at-review_at failed.
v0.4 (Refsdal's answer to 28386a38): the stalled count resets only on new evidence (a distinct instrument-output hash; for containers, a child change), never on an unchanged condition or new prose.
v0.4.1 (Refsdal's review R1, PR #8): the evidence hash covers declared matched_fields (values, not the verdict); undeclared fields are excluded; NC21 (c)/(d).

## 0. Principles this draft commits to
- Every mutating call takes `actor` and `expect_version`. A stale version fails loudly (StaleVersion). Nothing overwrites.
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

RedRef = (ledger_owner: Actor, red_id: RedId) | (observer: Actor, local_id: str, content_hash: Hash)
    # a peer's red isn't a RedRecord on the owner's ledger. The dedupe key is
    # content_hash when the red is the peer's own observation, red_id when it
    # refers to a red already on the owner's ledger. N observers of the same
    # observed output produce one event.
```
Containers (G2, settled with Refsdal):
- met needs a condition plus a current red, whatever the kind. A container with no condition can only be dropped, or amended to gain a condition. "Met when all children close" is not built in, because that would be met with no instrument.
- parent must be in the same owner's ledger. Cross-owner structure goes through request() pairs, never parent links, because custody means one owner can't re-parent or exit another's items.
- No orphans (NC20): a container's exit is refused while it has non-closed children, unless the same transition exits or re-parents each one.
- Surfacing: the last child closing sets the container's review_at to now, inside the same transition, recorded as a move (earlier, so free). That makes the container due, not met. The owner then takes met (if it has a condition and a red), dropped, or opens a new child.

## 2. Transitions (each is atomic and version-checked; owner's process only, except observe)
```
open(actor, kind, intent, review_at, condition=None, parent=None, draft=True) -> Item
    # kind=item requires condition. A draft blocks only MET; drafts can be dropped, swept and set dormant.
request(asker, deliverer, intent, condition, review_at) -> (deliver_item: owner=deliverer,
                                                             needed_item: owner=asker)   # NC10
    # each item lives in its owner's ledger; request is two opens linked by pair
amend(actor, id, expect_version, new_condition|new_review_at) -> Item
    # condition change refused if the instrument has a red or observation on record (NC3)
    # review_at moves (NC21), every move recorded:
    #   earlier: always free
    #   later, before due: free
    #   later, at or after due: counts as a review; it must carry an observation
    #     (what was checked, with what instrument). A bare due-time move is refused.
    #   k consecutive due-time moves without NEW EVIDENCE (k declared per Hearth, default 3)
    #     put the item on the human surface as "stalled". Not refused: stalled is legitimate,
    #     silent stalling isn't.
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
    # idempotent on red_ref; appends to the owner's event inbox; never writes an item
ack(event_id) -> Pending | Recorded{item_id, exit, at}      # readable by the event's sender (G3c)
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
    settle: Duration, deadline: Instant, act: command, executor: Actor) -> Item
    # refused unless BOTH controls have a green on the real (target) path AND a red on a broken one (NC17)
    # refused if deadline < now + settle (otherwise a correct move times out by construction)
disarm(actor, id, expect_version) -> Item
    # actor = executor once green is HELD (G3b, merged S1), or owner at any time before fire
fire(actor, id, expect_version) -> Item
    # actor = executor on held red or timeout, or owner (early rollback, merged call (a))
    # disarm and fire name the same version, so exactly one wins (NC18)
```
Settle rule, symmetric (NC19; merged M2): held green across `settle` means disarm. Held red across `settle` means fire immediately, without waiting for the deadline. Reaching the deadline with neither held is a timeout, and a timeout fires.
Firing claims the act under a lease (A1). After the act, the executor runs rollback_verification. If it fails, or the act stops partway, or the lease expires, the result goes to the human surface immediately (merged M1). Lease expiry also gives outcome_unknown. The executor never writes the owner's ledger; it reports via observe() plus the surface. The owner records the exit on return, using the executor's log as the instrument. If the owner never returns, liveness (6) catches it. Once disarmed, a later failure is a new item, never a rollback.

## 4. Reds and fingerprints (A5)
```
Control: command, declared_inputs: list[InputRef], matched_fields: list[FieldRef],
         expected_red: Matcher, expected_green: Matcher
    # matched_fields: the output fields the matchers read; the evidence hash for NC21 covers only these
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
sweep(owner) -> SweepReport{due: [Item], pending_events: [Event], errors: [SweepError]}
    # due = every non-closed item with review_at <= now (G1), plus outcome_unknown items
    # pending_events = inbox events with no ack Recorded (G4)
Ledger.declares: has_separate_index: bool, sweep_period: Duration
```
The sweep enumerates the store of record, never a derived index. It returns errors and never logs and skips. NC5 applies when has_separate_index is true; otherwise it is reported explicitly as N/A, never passed vacuously (S1).
Liveness (NC16): a checker outside the owner verifies that the owner's last sweep is within sweep_period + margin, AND that no inbox event is older than sweep_period + margin without an ack (G4). Either miss puts "X's ledger is unattended" on the human surface. NC16 must go red against a checker that only checks the process is alive.
Freshness (NC16b): the human surface shows "last full check at T, of N ledgers". The chain ends at the human reading a stale timestamp or a shrunken N. Nothing watches the human, and this spec says so.
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
