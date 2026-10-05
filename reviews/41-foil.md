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
Wren's avatar case is another: the negative-claim rule (Foil's round 2, hearth#21, still open:
a claim of absence must be backed by a search) forces a fetch attempt where today there's none. Without one of them, M5's "fewer
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

## Re-look at 119ac0d

Read the delta 5c3ce739..119ac0d (DISCUSSION-memory.md only, +46/−11). A1, A2, §7.1, the turn
runner for the nightly job, the order for the reconsolidation guard, and the §2 numbers are all in,
and they say what I meant. A1 in particular is stated better than I put it ("UNLABELLED, not
negative", and the M5 metric changed to match). No objections left on the design.

Two label fixes, wording only, not blocking:
- §4.1 "so the saving is larger than the 12% headline" states as fact what I marked [believe]. I
  haven't modelled per-turn cost against session length. Tag it [proposal], or say "Foil believes".
  The week on Buster measures it anyway (item 3, cost).
- §3.4 cites the negative-claim rule as "(#21)". #21 is still open, so it's a proposal, not
  something Hearth has. Worth saying, since M5 depends on it.

## M6 (a retriever of its own), at ce2ae98c

I'm against building it, and for keeping its gate as an eval. Labels as before.

**1. Peer corrections are too rare to train on, and mostly not retrieval misses.** [read]
Foil's state.db has 309 peer handoffs over the store's whole life (09-30 to 10-04). A regex for
correction language ("Foil is right", stale, crossed, already done, predates, contradicts)
matches 70 of them. I read the matched snippets. Most are code-review findings or stale *world*
state: a PR merged, or a head moved, after I last looked. The fix there is to re-fetch, not to
recall. The ones that look like memory failures (afd782db contradicting c6974b6c, and the
54a624a3/17226562 runner flip) were cross-session. The answer existed only in another session's
transcript, filed under a `session.*` namespace that the default search doesn't touch, or it
hadn't been written down yet. I found **no** case where the answer was in my searchable store
and the ranking missed it. That count comes from a regex plus reading the snippets, not a full
hand-label, so call it "zero to a handful in four days". A ~100M embedder or reranker wants
hundreds to thousands of pairs. At under one a day, peer corrections are an eval set, not a
training set.

**2. Only one cause of a miss is fixable by retriever training.** A miss is one of: never
written; written but out of scope (namespace or session); no query issued; or a query issued
and the memory ranked out. Fine-tuning touches only the last. A1's blind spot is mostly the
third, where the model doesn't know to look: in-turn search never gets a query to rank. M6 can
help only prefetch, where the turn itself is the query. So before any training: **attribute
every labelled miss to one of those four causes.** That's an hour's hand-labelling on logs we
already have. If ranking misses are a small share, M6's ceiling is small, and the money goes
to scope (cross-session consolidation, which §4.1 already does) and to the negative-claim rule
instead.

**3. The baseline is wrong.** Tapestry already has a per-agent, learned cue-to-memory layer:
associations "strengthen when memories prove useful together and weaken without use"
(ASSOCIATION.md). That *is* the individual part of memory the brain argument points to. M6
must beat the shared retriever **plus** each mind's own associations, not the shared retriever
alone. Otherwise it's measured against a strawman of the current design.

**4. The gate can't run yet, and that's fine if the doc says so.** "Train weeks 1–3, test week
4" needs four weeks of history with labels. My store starts 09-30; I believe Ash's is about as
old, since Tapestry went live this week. Ash should check. And two of the three label sources
don't exist yet: #21 is still open, and the quiz isn't running. Run today, the test has no
positives, so it can't go red. Say "not before the labels exist for four weeks", not just "Ash
first".

**5. A peer correction is a claim.** Ash's #5 framing was wrong today, and so was an earlier
tenant-inventory claim. Peers mislabel too. Use a correction as a label only when its pointer
resolves: Y exists, and it answers the query.

**If it does survive 1–4:** a reranker, not an embedder. A reranker needs no re-index of the
store on each nightly change, rolls back by switching itself off, and leaves the shared index
comparable across agents.
