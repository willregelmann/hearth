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
- Consolidation: background review **after every turn**. Foil measured it at ~37M of ~311M
  cache-read tokens (~12%) and ~140 of 1,292 calls on Foil's store [measured, Foil
  2026-10-04]. That's waking replay, the opposite of what brains do.
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
   the part that works. Make it the whole thing.

Cache interaction [measured, partly]: every eviction invalidates the cached prompt from that
point on. Claude Code's prompt cache expires after 5 minutes by default (our Hermes config
says `cache_ttl: 5m`), so a context touched after a gap pays a full re-write anyway. The
proposal: evict only at those cold boundaries, when the cache is already lost, so the
eviction itself is free. The ledger's same-session gap field measures exactly how often
that happens.

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
   **our own labels**. The labels come free: every unit we evicted and then had to fetch
   back from the transcript is a positive; every unit never touched again is a negative.
   The box has 31 GB RAM and **no NVIDIA GPU** [measured], so it would be a small model on
   CPU. That's fine for a nightly or cold-boundary job, too slow per turn.

My recommendation: build 1 first, log every eviction and every fetch-back from day one (so
the training set accumulates), then decide 2 vs 3 on the number. The question that decides
it is: "does a learned scorer reduce fetch-backs at equal context size?"

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

Measurement: the cost of one nightly job vs. ~12% per-turn overhead. Quality: run both on
the same day's transcripts and compare what each produces.

### 4.2 Reconsolidation guard

[proposal] Any fact or summary that's rewritten keeps its source pointer, and a rewrite that
drifts from the verbatim source is an error, not an update. Concretely, the nightly job
re-reads the cited lines for every fact it touches. That's the human remedy (external
records) applied where humans can't apply it.

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
