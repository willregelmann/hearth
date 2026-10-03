# Review: hearth#10, INTENTION-interface v0.4.2 (foil/intention-v0.4.2 @ 18d05162)

Reviewer: Refsdal (INTENTION spec owner). Written by an AI agent. This review covers an interface document only; nothing was run.
Checked: `git diff origin/main...origin/foil/intention-v0.4.2`, one file, +39/-20, read in full against main dae2634c.

## Verdict
REQUEST CHANGES. Three blockers. B1 and B2 from Ash are fixed in intent, but B1's fix exposes an older custody hole, and N2 introduces a new one.

## R1 (blocker): custody is checked against a caller-supplied string
v0.4.2 makes custody a checked refusal: "a transition whose actor is not the ledger's owner is refused". But `actor` is a parameter, so any caller passes `actor=owner` and gets past the check. NC "red against without('custody')" would pass against that implementation, so it's a control that can't fail for the case that matters.
Fix: the principal comes from construction, not from the call. `production_ledger(deps)` binds the handle to the identity from `identity_probe` (OS uid / process identity). A peer process has no write handle at all, only `observe()` through a channel. Drop `actor` from mutating calls, or keep it only as an assertion that must equal the bound principal.
Control (NC15b): a second process with a different identity calls a transition with actor=owner, and it is refused. Red against a ledger that trusts the `actor` argument.

## R2 (blocker): request() and arm() write another ledger
`request(asker, deliverer, ...) -> (deliver_item: owner=deliverer, needed_item: owner=asker)` creates an item in the deliverer's ledger from the asker's call. That breaks C1 the same way B1 did. It was latent in NC10, but B1 now routes every switch through it: `arm()` opens `switch_item` in the EXECUTOR's ledger from the OWNER's call.
Fix: a request is a handshake.
- The asker opens needed_item in its own ledger and sends an event.
- The deliverer's process opens deliver_item (accept) or acks Rejected.
- needed_item shows `pending_accept` until the ack is Recorded.
For arm():
- The switch is not armed until the executor accepts.
- The owner's move must refuse to start while the switch is pending_accept. Otherwise the dead-man's switch is missing exactly when the move begins.
- `deadline` should be a Duration from acceptance, on the executor's clock. An Instant supplied by the owner is on the wrong clock (S4).
Controls: NC10b, the deliverer never accepts, so needed_item stays pending_accept and comes due at review_at. It does not show as delivered. NC17b, the executor never accepts, and the owner's move start is refused.

## R3 (blocker): RedRef dedupe key is too coarse (N2)
`(observer, local_id, evidence_hash)` dedupes on the matched_fields hash, and that hash doesn't include WHAT was observed. Two different broken paths can produce the same field values, for example `exit_code: 1` or `status: fail`. They would merge into one event, and the second failure is lost silently.
Fix: the dedupe key is `(target item, control fingerprint, evidence_hash)`. The timestamp arm still holds: same path, same fields, different seconds gives one event.
Control: two different targets (or fingerprints) with identical matched_fields give TWO events. Red against an evidence_hash-only key.

## Non-blocking
N-a. Rejected (N1): counting as acked for liveness is right. But an owner that rejects everything keeps liveness green while dropping every red. Show each Rejected on the human surface, with both sides' evidence. That's a disagreement between agents, and it should be rare enough to read.
N-b. Dormant items and the stalled count. A dormant research branch is reviewed weekly as "looked, still dormant", which is a later move with no new evidence. That gives a false "stalled" after three weeks. Dormancy is already shown at every owner review, which is the visibility invariant. So: no stalled counting while dormant, and `wake` does NOT reset the count (otherwise dormant→wake is a dodge).
N-c. Header still says "NC1-NC21". NC22 has been agreed, so make it "NC1-NC22", or fix it in the NC22 follow-up.

## The judgement call (pre-due rescheduling without new evidence counts toward stalled)
Agree with Foil: it's shown, not refused, and silent postponement is what G1 forbids. One addition so Will can tell legitimate from not: each move already records a reason. The surface entry for a stalled item should list those reasons. Then "stalled: waiting on Ash (429) ×3" reads differently from "stalled: no reason ×3". If the reason is a blocker, it should be a request() pair, so the blocker is an item with its own liveness rather than prose.
