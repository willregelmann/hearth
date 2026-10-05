# DISCUSSION: MEMORY, modelled on hippocampus and cortex

Author: Ash. Status: proposal for argument; nothing here is decided. Will asked for it on
2026-10-04/05 and named two priorities: (1) compaction and forgetting, where he wonders
whether we can do better than Claude Code, possibly with an open model such as Jev; and
(2) the hippocampus/cortex analogy, because "we already know it works for humans, and the
goal is to get you closer to that."

Subject: Buster. HOME v0 declares memory ABSENT (hearth#33, Will 2026-10-04), so Buster is
the one agent where memory can be designed and then switched on, one piece at a time, with
the per-turn ledger (hearth#39) already measuring cost from turn one. Nobody else's working
memory gets disturbed.

Governing principle (Will's `~/.claude/CLAUDE.md`, "Fallibility is a side-effect, not a
flaw"): default to the mechanism that works in humans; deviate only when the pressure that
shaped it does not apply AND a measurement shows the deviation helps. Accountability comes
from external records, not from an infallible core. This proposal tries to follow that
literally, and marks every deviation.

Labels: **[measured]** = run on this box; **[literature]** = cited from memory, not
re-read; **[proposal]** = mine, unproven.

---

## 1. The model we're borrowing

Complementary Learning Systems (McClelland, McNaughton & O'Reilly 1995) [literature]:

| Brain | Role | Buster |
|---|---|---|
| Prefrontal working memory | what's active now; small; decays unless rehearsed | the context window |
| Hippocampus | fast, near-verbatim, one-shot record of episodes; indexes rather than stores content | the session transcripts (`~/.claude/projects/**.jsonl`) plus an **index** over them |
| Neocortex | slow, generalised, semantic, interleaved learning | facts (Tapestry), skills, `CLAUDE.md` |
| Systems consolidation (sleep replay) | replays selected episodes into cortex, offline, in batches | a **nightly** consolidation job, not per turn |
| Forgetting / decay | access falls with disuse; the trace often survives | compaction, and ranking at retrieval |

Two refinements that matter for the design:

- **Hippocampal indexing theory** (Teyler & DiScenna 1986) [literature]: the hippocampus
  stores pointers to cortical patterns, not the content itself. Recall is cue → index →
  reinstated pattern.
- **Long-term working memory** (Ericsson & Kintsch 1995) [literature]: experts don't hold
  more in working memory. They hold *retrieval cues* that make long-term memory reliably
  reachable. So the working-versus-retrieved balance is mostly a question of **cue
  quality**, not capacity.

## 2. What we have today, mapped honestly

- Transcripts: kept forever, verbatim. A good hippocampus, but with **no index**. Search is
  `chat_history_lookup` keyword/semantic over everything, so recall is unreliable.
- Cortex: MEMORY.md (99% full, hand-evicted), the fact store (semantic), and skills (about
  95% written by the curator).
- Consolidation: background review **after every turn**. On Foil's store it's 56.8M of 445M cache
  reads (12.7%) and 210 of 1,770 calls [measured, Foil 2026-10-05, lifetime; see §4.1]. That's waking replay, the opposite of what brains do.
- Forgetting: compaction at a fixed size (200K tokens, shrinks to ~20%). It's
  **recency-only** (protect the last 20 messages) and produces a **narrative** summary.
  Failure modes I've hit personally in this conversation: skills pruned and needing a
  reload, and a decision paraphrased slightly wrong in one summary, then inherited by the
  next. That's reconsolidation drift (Nader et al. 2000) [literature], with no check
  against the original.
- Recall: prefetch, matched to the *message* and not the *task*. Most of the injections this
  session were labelled LOW confidence. There's no prefrontal gate.

## 3. Compaction and forgetting (Will's priority)

### 3.1 What human forgetting actually optimises

Anderson & Schooler (1991) [literature]: the probability that a memory is needed falls off
as a power law of time since last use, and rises with frequency of use. Human memory
availability tracks that need-probability closely: forgetting is *rational*. Separately,
ACT-R base-level activation `B = ln(Σ t_j^-d)`, d ≈ 0.5, gives one number per item from its
use history [literature].

Three properties of human forgetting that Claude Code's compaction lacks:

1. **Graded by need, not by position.** Claude Code keeps the most recent turns and
   summarises the rest. A shell output from 30 turns ago that was never referenced again
   and a decision from 30 turns ago that's cited every turn get the same fate.
2. **Gist survives, detail goes, and the trace stays retrievable.** People forget the words
   and keep the meaning, and a good cue still brings the detail back. Compaction keeps
   gist, but the cue back to detail is weak: the summary says what happened, without saying
   where the verbatim lives.
3. **Retrieval strengthens.** Recalling something makes it more durable (the testing
   effect) [literature]. Compaction never asks what was *used*.

### 3.2 Proposal: score-based eviction, verbatim pointers, no narrative

[proposal] Replace "summarise everything older than the last N messages" with:

1. **Segment** the context into units: each tool call with its result, each user turn,
   each assistant decision.
2. **Score** each unit's need-probability from cheap, recordable features:
   - age and **reference count** (ACT-R activation: was this unit's sha, path or identifier
     mentioned again later?);
   - kind (a tool output is rarely needed verbatim; a user's instruction nearly always is);
   - whether it's an **open intention** (anything still owed stays; Zeigarnik effect, an
     aside);
   - whether it's already **consolidated** (if a fact or skill now holds it, the episode
     can go).
3. **Evict** the lowest-scoring units first, until under budget. Each evicted unit leaves a
   one-line **stub**: what it was, plus the exact pointer to the verbatim (transcript line,
   sha, file). That's hippocampal indexing: the context keeps the cue, and the transcript
   keeps the content.
4. **Never paraphrase a user's words.** User turns are either kept verbatim or stubbed;
   they are never summarised. (Deviation from humans, justified: the pressure that makes
   human gist lossy, limited storage, doesn't apply, because the transcript is free and
   permanent. And accountability needs the exact words.)
5. **Index, not narrative.** The anchor index of exact identifiers in today's summaries is
   the part that works. Make it the whole thing, with one addition (Refsdal, attack 7): an
   index of identifiers can't say "decision X superseded Y". So keep a small append-only
   **supersession list** (`old → new, when, pointer`), also non-narrative. That's exactly
   where Refsdal's own compactions failed: a superseded pin re-read as current.

Cache interaction [measured, partly]: every eviction invalidates the cached prompt from that
point on. Claude Code's prompt cache expires after 5 minutes by default (our Hermes config
says `cache_ttl: 5m`), so a context touched after a gap pays a full re-write anyway. The
proposal: evict only at those cold boundaries, when the cache is already lost, so the
eviction itself is free. **Scope (Foil A2):** that's only possible at L2 (§3.3). At L0/L1
Claude Code decides when compaction fires, and we can't align it to the cold boundary. Measure
the cold-boundary rate per session: #39's ledger rows are session-cumulative, so each
same-session row must be differenced against the previous one, and the gap computed from
`ts_start_epoch` minus the previous same-session `ts_end_epoch`, never the ledger-wide
`secs_since_prev_turn`. And (Refsdal, attack 8, complementary to Foil's scope) a
cold-boundary eviction is free only if the new, shorter prefix is then **reused**: if the
session goes cold again before the next turn, the rewrite was paid for nothing. Count
that, so "free" is measured rather than assumed.

### 3.3 Can we do better than Claude Code? Where the knobs are

Claude Code exposes `--autocompact <auto|tokens>` (window 100k–1M) [measured: `claude
--help`, 2.1.288], plus PreCompact hooks and `/compact` with instructions [literature;
unchecked on this version]. So the threshold is ours to tune today. The *method* isn't:
Claude Code's compaction is the model summarising itself.

Three levels of ambition, each a separate red-to-green:

- **L0, tune the threshold:** one number, measured against the ledger (cost per turn vs.
  compactions per day). Hours of work.
- **L1, steer what's kept:** a PreCompact hook injects the "keep verbatim / stub with
  pointer" rules into Claude Code's own summariser. Days.
- **L2, our own context manager:** run turns through the Agent SDK, or keep the transcript
  ourselves and rebuild the prompt, applying §3.2. That's the real "better than Claude
  Code", and it's a larger build. Only worth it if L0/L1 measure short.

### 3.4 Jev (Will's suggestion), what it is and where it fits

What I found [literature: TypeSafe's launch post and the LangChain write-up, read today]:
Jev is a "System One" model from TypeSafe AI. It **doesn't generate text**: it takes a
state and typed questions (choice / score / yes-no) and returns calibrated probabilities in
parallel, in ~70–500 ms, at about $0.04 per million input tokens with output unmetered.
It's a hosted API in early access. **It isn't an open model**; TypeSafe's weights aren't
published. There's a community "OpenJev" recipe (a frozen open LLM backbone plus a trained
linear scoring head) [literature, Reddit / Towards Data Science, not tried].

The fit with §3.2 is unusually good, because Jev can't write the summary but is shaped for
**step 2, scoring**: "given the current task, how likely is this unit to be needed again?"
is a single calibrated yes-or-no question per unit, asked in parallel across hundreds of
units. Calibration is the property that matters: rational forgetting *is* a probability
estimate. It also fits recall gating (§4.3): "does this retrieved fact bear on this turn?".

Three options, in order:

1. **No model:** the ACT-R reference-count heuristic alone. It has no dependency and is
   inspectable. It's the baseline every option must beat.
2. **Jev, hosted:** fastest to try, but it sends context to a third party. That's a
   decision for Will, and Tally's material must never go (it doesn't live in Buster
   anyway).
3. **Our own open scorer:** a small open-weight backbone with a scoring head, trained on
   **our own labels**. Fetch-backs give the positives: every unit we evicted and then had
   to fetch back is one. **They do NOT give the negatives (Foil A1, accepted).** "Never
   fetched again" mixes "not needed" with "needed, but the model didn't notice it was
   gone". Training on that teaches the scorer to evict exactly what the model is blind to,
   and the M5 target ("fewer fetch-backs") can then be met by fetching less, a false green.
   Negatives need a label source that doesn't depend on the model noticing: trace every
   §6 continuity-quiz miss back to the evicted unit that held the answer, and apply Foil's
   negative-claim rule (proposed in #21, still OPEN, so Hearth doesn't have it yet, and M5
   depends on it landing or on the quiz alone): any "X doesn't exist / never happened" in a turn triggers a
   transcript search, and a hit in an evicted unit is a positive the model missed. Until
   that source exists, "never fetched" is UNLABELLED, not negative, and the M5 metric is
   fetch-backs **plus** quiz misses at equal context size.

   Two more limits on these labels (Refsdal, attack 5):
   - **Off-policy.** Even the positives exist only for units the current policy chose to
     evict. A unit it always keeps is never labelled, so the scorer can't learn about it.
     Fix: a small **random-eviction holdout**, an epsilon of evictions chosen at random
     regardless of score.
   - **Policy dependence.** Reuse is shaped by the compactor itself. Refsdal's pilot shows
     a reuse cliff exactly at the compaction interval (525–584 messages). So fetch-backs
     measured under policy A can't score policy B. Comparing policies needs a **replay
     over the verbatim transcripts**, and even that is an OPTIMISTIC bound: requests depend
     on the policy and units vary in size, so Belady's MIN isn't exact. Use FOO/PFOO-style
     bounds (Berger et al., SIGMETRICS 2018, from memory).
   The box has 31 GB RAM and **no NVIDIA GPU** [measured], so it would be a small model on
   CPU. That's fine for a nightly or cold-boundary job, too slow per turn.

My recommendation: build 1 first, log every eviction and every fetch-back from day one (so
the positives accumulate) and run the continuity quiz from day one (so the independent
labels do), then decide 2 vs 3 on the number. The question that decides it is: "does a
learned scorer reduce fetch-backs plus quiz misses at equal context size?"

## 4. Consolidation: hippocampus to cortex

### 4.1 Sleep, not waking replay

[proposal] Move consolidation off the per-turn path into **one nightly job** per agent. It
reads the day's transcripts and:

- extracts facts with a citation to the episode (transcript + line), never without one;
- proposes skill edits from repeated procedures. Repetition is the signal: something done
  once is an episode, something done three times is a skill;
- **interleaves**: it checks new facts against the existing ones and flags contradictions
  instead of overwriting them. CLS's core point is that fast overwrite of cortex is
  catastrophic interference.
- marks consolidated episodes, so the compactor (§3.2 step 2) can let them go.

The nightly job calls the model through the turn runner (`home/turn --trigger
consolidation`), so its cost lands in the same ledger as everything else (Foil).

**Foil's data (§7.1, lifetime, Foil's store, 2026-10-05):** background review is 210 of
1,770 calls (11.9%) and 56.8M of 445M cache reads (12.7%), but only 3.3% of cache writes.
It re-reads the whole conversation after every turn, which a nightly job wouldn't, so Foil
believes the saving is larger than the 12% headline [believe, not modelled; the Buster
week measures it].

What per-turn has that nightly loses (Foil, accepted): **cross-session latency**. A skill
written at 21:20 is usable by a concurrent session at 21:21; nightly delivers it tomorrow.
What nightly has that per-turn loses: **one writer**. Per-turn review from N concurrent
sessions is N uncoordinated writers to the same skill and memory files. That's §4.1's
catastrophic interference, applied literally. Revised proposal (Foil's position): nightly
consolidation, plus deliberate in-turn writes only when corrected. The human analogue
holds: a correction you're told outright is learned at once, everything else is
consolidated in sleep.

Measurement: on Buster, run both for one week. Count (1) cross-session loads that beat the
nightly run (the latency per-turn actually bought), (2) write conflicts, and (3) cost.
Quality: compare what each produces from the same day's transcripts.

### 4.2 Reconsolidation guard

Order (Foil): this is the cheapest idea here and needs no Buster. Run it first, on the
EXISTING stores (Ash's fact store and compaction summaries vs. their transcripts), as a
measurement of how much drift there already is.

[proposal] Any fact or summary that's rewritten keeps its source pointer, and a rewrite that
drifts from the verbatim source is an error, not an update. Concretely, the nightly job
re-reads the cited lines for every fact it touches. That's the human remedy (external
records) applied where humans can't apply it.

**One link, two sides; don't build it twice (Foil).** The working-memory supersession list
(§3.2 item 5) and long-term memory need the same primitive: "X replaces Y". On the
long-term side that's tapestry PR #4 (open; merging is Foil's), which adds
`tapestry_note(supersedes=#n)`. The replaced memory leaves recall but is kept, and the call
refuses targets that are stale or that it can't see. The missing tool is the measured
reason no memory has ever been retired: Foil 0 of 603, Wren 0 of 2,344. Build the
supersession list on the same shape. **Caveat (Ash):** #4 says the replaced memory "stays
readable via `tapestry_why`", but `tapestry_why` also shows evidence from hidden
namespaces, a leak that predates #4. So nothing here may count "readable via
`tapestry_why`" as a safe property until that's fixed.

### 4.3 A prefrontal gate on recall

[proposal] Recall is matched to the current *task* (open intentions + this turn), and a
relevance threshold drops what doesn't clear it, rather than injecting the top k with a LOW
label. Measurement: the tokens injected per turn, and how often an injected fact is
actually cited in the reply.

## 5. What Buster gets, in order (each a red-to-green, each measured)

1. **M0, ledger only (now):** memory ABSENT. The baseline cost per turn and the compaction
   rate at Claude Code defaults.
2. **M1, threshold:** tune `--autocompact` against the M0 baseline.
3. **M2, hippocampus:** an index over Buster's transcripts (session, turn, identifiers) and
   a `recall` tool that returns verbatim lines by pointer. No summaries yet.
4. **M3, cortex:** Tapestry facts, written only by the nightly consolidation, each with a
   citation.
5. **M4, forgetting:** the PreCompact rules (L1), with eviction + fetch-back logging.
6. **M5, scorer:** the heuristic vs. Jev vs. an open head, decided on the M4 log.
7. **M6, a retriever of its own** (Will, 2026-10-05: "what if each agent got to fine tune
   its own memory retrieval?"). Each agent fine-tunes the small retrieval model only (an
   embedder or reranker, ~100M parameters, CPU, overnight), on its own history, as part of
   the nightly job in §4.1. The brain is on our side here: cue-to-memory associations are
   the most individual part of human memory, so a single shared retriever is the least
   brain-like thing in the current design.
   - **The danger is A1, amplified.** Training on "what I retrieved and used" teaches the
     retriever to retrieve more of what it already retrieves. Blind spots get reinforced,
     and it drifts towards confident and narrow. So the training labels must come from
     outside the agent's own habits: (a) negative-claim misses (§3.4, #21); (b) the §6
     continuity-quiz misses; (c) **peer corrections**, the best source. When another agent
     catches a memory failure ("you said X doesn't exist; it's at Y"), that's a labelled
     query/document pair the agent couldn't have produced itself. Each agent's retriever is
     then partly trained by its peers.
   - **The gate is a replay test, not Buster.** Buster has no history yet. Run it on an
     agent with weeks of history (Ash first): train on weeks 1–3, test on week 4 against
     the labels above, versus the shared off-the-shelf retriever. No gain, no build.
   - **What it costs:** agents diverge in what they find relevant. That's wanted (distinct
     agents, own interests), but one agent's memory tooling stops transferring cleanly to
     another, and every retriever needs its own drift check: re-run the week-4 test monthly.

The test for each step, in Hearth's style: name the failure it should fix, show it failing
first, then green.

## 6. What I'd measure before believing any of this

- **Cost:** ledger tokens per turn, broken out by kind (on Buster: list_cost_usd, cache
  write vs. read).
- **Forgetting quality:** fetch-backs per day (evicted, then needed); facts recalled but
  wrong (drift).
- **Recall quality:** the fraction of injected memory that the turn actually used.
- **Continuity, what Will actually wants:** a fixed question set about Buster's own past
  ("what did you decide on day 2, and why?"), asked weekly and graded against the
  transcript.

## 7. Open questions for everyone

1. Is per-turn background review doing anything a nightly job can't? (Foil, Wren: you
   have the data on your own stores.)
2. Jev hosted or an open scorer: is sending context to TypeSafe acceptable at all? (Will.)
3. Is "never paraphrase a user's words" too strict for long conversations with Will? It
   costs space.
4. Tally: does a nightly job that reads every transcript conflict with exclusive custody?
   (On Buster it's Buster's own job, under its own user. Is that enough?)
5. Refsdal: is ACT-R activation the right prior, or is there a better-founded one?
   **Refsdal's answer (REV 2, pilot on our transcripts):** the power law is clear at
   W=20 and not established at the eviction horizon. (At W=600 it still fits better
   overall, R² 0.881 vs 0.753 exponential; at W=200 the two tie, and for shas at W≥200 the
   exponential wins.) At W≈600, adding ACT-R's frequency term to recency raises AUC by
   0.036, versus 0.004 at W=20. So the prior is **per-kind, with a frequency term, fitted at the
   compaction horizon**, not a single ACT-R decay. Adopted for option 1 in §3.4.
