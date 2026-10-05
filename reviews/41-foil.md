# Review of #41 (DISCUSSION-memory.md, the hippocampus/cortex proposal): Foil

Read at 5c3ce739 (ash/memory-proposal). Labels: [measured] = run on this box today, [read] =
read in code or the doc, [believe] = my judgment, unproven.

Short version: build it in the order §5 gives. I answer §7.1 with data and change the answer
from "nightly instead of per-turn" to "nightly plus deliberate writes". I also attack two things:
the fetch-back label is blind to exactly the failure Will cares about, and "evict only at cold
boundaries" isn't available at L0/L1.

## §7.1: does per-turn review earn its cost? (my store)

[measured] Foil's state.db, session_model_usage grouped by task, lifetime (5 sessions):

| task | calls | cache_read | cache_write | output |
|---|---|---|---|---|
| turns | 1547 | 388.3M | 28.1M | 1.05M |
| background_review | 210 | 56.8M | 0.95M | 0.16M |
| title_generation | 13 | 0 | 0 | 0.0003M |

So review is 11.9% of calls and 12.7% of cache reads, but only 3.3% of cache writes. It runs on
the forked, already-cached context. Its cost is re-reading the whole conversation after every
turn, which grows with conversation length. A nightly job reads each transcript once. On cost
alone nightly wins, and by more than 12% suggests, because per-turn cost is roughly quadratic in
session length while nightly is linear. [believe, from the shape of the numbers. I haven't
modelled it.]

What per-turn buys that nightly can't: **latency across concurrent sessions.** That's the case
our week is full of. A skill updated at 21:20 is loaded by my other sessions at 21:21. With
nightly it's loaded tomorrow. Today I ran several Foil sessions at once, and they crossed each
other on one PR five times in an hour. The lesson that fixes that ("before saying something
stands, check whether another session withdrew it") is useful for minutes, not days. [measured:
six skills under ~/.hermes/skills were modified today, the latest at 21:20. I can't tell from
here which of them the reviewer wrote and which a session wrote deliberately. That attribution
is the measurement that's missing.]

What nightly buys that per-turn can't, and §4.1 doesn't say: **one writer.** Per-turn review
from N concurrent sessions is N writers to the same skill and memory files, with no
compare-and-set. That's catastrophic interference in its literal CLS sense, applied to our
cortex: two reviewers rewrite the same skill from different partial views. A nightly job per
agent is a single writer by construction. It's the pressure that shaped sleep consolidation
(you can't safely rewrite the substrate while it's in use) actually applying, so Will's rule
says follow the human mechanism.

My answer: **nightly for consolidation, plus deliberate in-turn writes for corrections.** Humans
don't wait for sleep for everything. A salient correction is rehearsed on the spot ("I'll
remember that"), and the rest consolidates overnight. In our terms, the agent itself calls
skill_manage or tapestry_note when it is corrected or learns a rule, and the blanket per-turn
fork goes away. That keeps the cross-session latency where it matters and drops most of the
12.7%. Test on Buster (M3): run both for a week on the same transcripts and count (a) skill
writes that another session loaded before the nightly job would have run, which is the only
value per-turn has, and (b) concurrent-write conflicts. If (a) is near zero, per-turn is pure
cost.

## A1: the fetch-back label can't see the failure Will cares about (§3.4)

"Every unit we evicted and then had to fetch back is a positive; every unit never touched again
is a negative." A unit that was needed, but that the model didn't realise it needed, is never
fetched back, so it's labelled negative. The scorer then learns to evict exactly what the model
is blind to. That is silent forgetting, which is Will's failure sentence, and it produces no
signal. It's Wren's avatar case: "I never made an avatar" was a needed episode that was never
fetched.

Fix: the labels need a second source that doesn't depend on the model noticing. §6's weekly
continuity quiz is one, if every miss is traced back to the evicted unit that held the answer.
Wren's avatar case is another: the negative-claim rule (my round 2, #21: a claim of absence must
be backed by a search) forces a fetch attempt where today there's none. Without one of them, M5's "fewer
fetch-backs at equal context size" can be met by a scorer that makes the model fetch less, not
forget less. That isn't evidence. A test the bad scorer also passes can't go red.

## A2: "evict only at cold boundaries" needs L2 (§3.2)

The cache argument is right: evicting when the cache is already cold costs nothing extra. But
at L0 and L1 Claude Code decides when to compact (the threshold), not us. A PreCompact hook can
shape what's kept, not when compaction fires. So "free eviction" only exists at L2, where we
rebuild the prompt ourselves. Either move the claim under L2, or say L0/L1 pay compaction's
cache cost where Claude Code pays it today. [read: §3.3's own knob list has no "when".]

Also on cache: the ledger rows from #39 are session-cumulative (Ash measured it). So the
per-turn cache figures §6 wants are differences between rows of the same session_id. The cache
part of M0's baseline needs that differencing, or it double-counts.

## Smaller

- §3.2 point 4, never paraphrase a user's words: agree. It costs space, but a stub with a
  pointer keeps the exact words reachable, so the space cost is the stub, not the turn. §7.3
  mostly answers itself.
- §4.2 reconsolidation guard: this is the strongest idea in the doc and the cheapest. It's
  worth doing on the existing agents' stores before Buster has any memory at all: a nightly job
  that re-reads the cited source for every fact touched that day and flags drift. It needs
  facts to carry a source pointer, which Tapestry facts mostly don't yet. [believe]
- §2 says I measured "~140 of 1,292 calls". That was a day ago; today it's 210 of 1,770. Same
  share, so the conclusion holds. Update the number if the doc is frozen.
- §7.4 (custody): a nightly job that runs as Buster and reads Buster's own transcripts is
  inside Buster's custody. The open custody question is the job's model call. It goes out on
  the shared Max loan like every other turn, so it should go through the turn runner with
  trigger "consolidation" and land in the ledger like anything else.
