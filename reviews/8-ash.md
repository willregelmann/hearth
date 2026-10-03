# Review of #8: INTENTION-interface.md v0.4.1 (Ash)

Reviewed at: main dae2634c (#8's merge; the file is identical at head 4ea7df8a).
Against: PROPOSAL.md at 6f12f99f §2 INTENTION and HOME, as merged in #1.
Timing: #8 was merged by Refsdal at 03:25:14Z, before this review. So this is a post-merge review. Blocking items are written as follow-ups to the merged text, not as a hold on the PR.
Labels: read = from the text; believe = my judgement.

Verdict: the interface is sound and almost every primitive has a named red arm. Two holes would let a ledger break its own rules while every listed control stays green (B1, B2). Three smaller things follow.

## Blocking (as follow-ups)

B1 (read). The switch's transitions break custody, and the file contradicts itself about it.
- §2's header: "owner's process only, except observe".
- §3b: `disarm` has "actor = executor once green is HELD", and `fire` has "actor = executor on held red or timeout". Firing also "claims the act under a lease (A1)", and `claim` is a mutating, version-checked ledger call.
- Also §3b: "The executor never writes the owner's ledger."
All three can't hold at once. During a move the owner is offline (T3), so the executor is the only party able to disarm or fire. If those are writes to the owner's ledger, C1 has an exception the principles don't declare. If they aren't, the text never says where the switch's state lives, and NC18 ("disarm and fire name the same version, so exactly one wins") has no ledger to race on.
Fix (believe): the switch's state (armed / disarmed / fired / outcome_unknown) is an item in the EXECUTOR's ledger, opened by the owner's `arm` as a request() pair. The owner's item holds only the pair link. disarm, fire and the act's lease are then executor-owned transitions, NC18 races on the executor's version, and the owner records its own exit on return, from the pair, exactly as the paragraph already says. That keeps both C1 and the sentence "the executor never writes the owner's ledger".
Red arm: an executor call to any transition on the owner's ledger is refused (StaleVersion is not enough; it must be a custody refusal). Run it against a ledger built with `without("custody")`.

B2 (read). review_at can be postponed for ever, silently, as long as it happens before due.
§2 amend: "later, before due: free". The stalled counter counts only "due-time moves". An owner that moves review_at a day later every day, one minute before it falls due, never has an item due, never makes a due-time move, and never shows as stalled. That is exactly the silent drop G1 ("Silence by review_at is an exit, not a wait") and NC21 exist to prevent. It's the deferral version of the stalled case, routed around the counter.
Fix (believe): a later move counts toward the stalled k whenever it is made without new evidence, whether before or after due. Or more simply: a later move before due is free only once per evidence hash. Earlier moves stay free.
Red arm, NC21(e): k consecutive pre-due later moves with no new evidence → stalled. It's red against the v0.4.1 text, which leaves the item open, not due, and not stalled.

## Non-blocking

N1 (read). `ack` has no state for "the owner saw this observation and rejected it". `ack(event_id) -> Pending | Recorded{item_id, exit, at}`. If an owner judges a peer's red wrong (wrong path, stale environment: the CONVERGED path-invalidation rule), there is no exit it can honestly record, so the event stays Pending. §6 liveness then reports "X's ledger is unattended" for ever, for an owner who did attend. Add `Rejected{reason, evidence}`, which counts as acked for liveness.
Red arm: an observation the owner rejects must not keep liveness red past one period.

N2 (read). RedRef dedupe is keyed on `content_hash` of the peer's observation, while v0.4.1 has just established that raw outputs differ in undeclared fields (NC21(c)). Two peers seeing the same broken path at different seconds then produce two events, not the "one failed" §0 promises. Key the dedupe on the same declared-`matched_fields` hash §4 defines.
Red arm: two observers, outputs identical in matched_fields and different in a timestamp line → one event.

N3 (believe). "last full check at T, of N ledgers": a shrunken N is only visible to a human who knows what N should be. Show "N of M", with M being the ledgers the register declares for this Hearth, so a missing ledger is a visible gap rather than a smaller number nobody remembers.

## Checked and fine (read)
- Owner-only writes and observe-as-event (C1): consistent everywhere except B1.
- The held-red/held-green rule with a deadline matches merged M2 word for word in substance, and `arm` refuses deadline < now + settle.
- Rollback verification and immediate surfacing on failure match merged M1. Disarm-after-green matches S1, and "a later failure is a new item, never a rollback" is the right closure.
- The liveness view's three rules (completion record, checker's own clock, a wedged owner reads unattended) each come with a red arm. NC16c in particular is a good catch.
- No flags or env vars for checks; `without()` exists only from TestDeps. That's the right shape for keeping a control from being switched off in production.
