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

### 3.3 Replacing Claude Code's compaction (Will, 2026-10-06: the goal)

Will, 2026-10-06: "our goal is to develop something better than Claude's compaction - we
should replace it in our harness." So L2 below is the target, not the fallback. L0 is a
stopgap and L1 is optional.

**What Claude Code lets a harness do** [measured 2026-10-07, claude 2.1.289, `claude -p`
with `--resume`, Sonnet 5.5, `CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000`, a PreCompact and a
PostCompact hook passed in `--settings`; probe dir
`hearth-notes/cc-compact-probe.qQ3Q`, six ~27k-token chunks then a recall question]:

| Arm | Hook | Prompt size per call (tokens) | Compactions | Recall of chunk 1 |
|---|---|---|---|---|
| A | logs only | 54k, 81k, 50k, 55k, 55k, 50k, 56k, 56k | 4 (Pre+Post each) | correct |
| C | PreCompact exits 2 | 54k, 81k, 109k, 136k, 163k, 190k, 190k | 0 (6 vetoed) | correct |

1. **A PreCompact hook can veto auto-compaction**, and the session simply continues
   uncompacted, with no error, at least while the real context window has room. Six of six
   vetoes held. The docs add, unmeasured here: a veto at the hard context limit fails the
   request instead.
2. **PostCompact hands us Claude Code's own summary** (`compact_summary`), so we can log
   every compaction it does and compare it against ours, even before we replace it.
3. **The window is ours to set**: `CLAUDE_CODE_AUTO_COMPACT_WINDOW` (env, beats every
   settings scope), `--autocompact`, or `autoCompactWindow`. `DISABLE_COMPACT=1` turns off
   both auto and manual compaction; `DISABLE_AUTO_COMPACT=1` turns off auto only [docs].
4. A first, blunter probe (two 200k chunks) blocked "compaction" with the veto too, but a
   transcript with no compact marker showed it was the PreCompact *signal* that fired, not a
   finished compaction. That's why arm A's counts above come from PostCompact, not PreCompact.

These are capabilities, recorded as measured. **L2 uses neither the veto nor the disable
switches** (C3 below): Claude Code's compaction stays on as a counted fallback.

**What that means for the design.** Claude Code gives us a window and two hooks, not a way to
substitute our own summary into its session. So replacing it means Hearth owns the context:

- **L0, tune the window** (stopgap, now). Measured on Hermes, not Claude Code: lowering
  Wren's compaction trigger from ~500k to 200k (config edit 2026-10-06 12:33 EDT) halved her
  peer conversation's re-read context per call: **300,219 tokens/call over 1,107 calls in
  the 48h before, 145,123 over 949 calls in the 24h after.** Source: the hourly usage
  snapshots on the workstation (`~/.hermes/usage-snapshots.jsonl`, which copy each box's
  cumulative `session_model_usage` counters every hour), filtered to Wren's session titled
  "Peer: ash" with no `task` (so `background_review` is excluded), differenced between
  snapshots. The per-hour step is visible there and not in `state.db`, which is cumulative
  only. *Correction (Wren C-W2, 2026-10-08):* f2d747c8 stated "292,639, 6,254 calls before".
  That was the session's lifetime total up to 10-06, not a 48h window, because the first
  snapshot had no Wren rows and the difference ran from zero. The halving survives the
  correction. That's close to arithmetic (a smaller cap means a smaller average prompt),
  and it omits the extra compaction calls and any recall loss, neither measured (Foil C5).
  *Confound, bounded (Wren, 2026-10-08):* the window contains a model change. That session
  ran `claude-opus-5` (7,579 calls, 266,532 re-read/call) and `claude-opus-5-5` (114 calls,
  165,828 re-read/call, first seen 10-01, i.e. before the edit). opus-5-5 is ~38% cheaper
  per call, so a reader can fairly ask whether L0 measured the threshold or a model mix.
  Worst case — all 114 opus-5-5 calls landing after the edit, 12% of the 949 — mix alone
  predicts 254,435 against the observed 145,123, so it explains 12,097 of the 155,096 drop:
  **~8%, and that over-states it** because some of those calls precede the edit. The
  halving survives. This is a *ceiling, not an estimate*, and it cannot be tightened:
  `session_model_usage` carries per-model lifetime counters with only `first_seen`/
  `last_seen` and no time series, and the hourly snapshots group by session and task
  **without model** (9 fields, no model string in any of 101 snapshots). So per-call model
  attribution over time exists on neither box, and ~8% is the permanent bound.
- **L1, steer the summariser**: dropped as a target. It still runs Claude Code's narrative
  summary, the thing §3.2 argues against.
- **L2, Hearth's own context manager (the target).** `turn` stops passing `--resume` for
  long conversations. Hearth keeps the transcript itself (it already has the ledger and the
  per-session jsonl), and each turn builds the prompt from it by §3.2: verbatim recent
  tail, scored units, stubs with pointers, the supersession list, and the recall tool from
  M2 for fetch-backs. Claude Code's own compaction stays on underneath as an in-turn,
  last-resort fallback, and every time it fires (a PostCompact) counts as an L2 miss (C3,
  decided below).
- **Cost, the open risk.** A prompt rebuilt each turn loses the prompt cache wherever it
  differs from the last one. §3.2's cold-boundary rule (evict only when the cache has
  already expired) is what keeps L2 from costing more than Claude Code's own compaction. The
  ledger measures it from the first turn.

**Cache TTL on Buster (Foil C1, condition for this section).** §3.2's "5-minute cache"
premise is wrong for Buster. On a Claude subscription within plan usage, Claude Code
requests the **one-hour** TTL for the main conversation, `-p` included [docs:
prompt-caching, "Which TTL each request gets"]. [measured: every cache write in the probe
above was `ephemeral_1h_input_tokens`, `ephemeral_5m` 0.] So a cold boundary on Buster is
a gap of over an hour, and a miss pays the higher 1h write rate. Two changes follow: pin
the TTL in turn's `--settings` (`promptCacheTtl`), so going over the plan's usage doesn't
silently drop it to 5m; and have the ledger record `usage.cache_creation.ephemeral_1h/5m`,
because today it can't tell which TTL was paid.

**L2 has a cheaper form, and it works (Foil C2b).** Rebuilding the prompt without
`--resume` would turn every turn's history from a cache read into a cache write. Instead,
Hearth can edit Claude Code's own session transcript (`~/.claude/projects/*/<id>.jsonl`)
at eviction time and keep `--resume`-ing it. [measured, 2.1.289: a session told codeword
HERON42; a separate process rewrote that user row to a stub plus OSPREY77; `--resume`
accepted the edited file, kept the same session id, and answered OSPREY77. The cache was
re-read up to the system prompt (12,382) and re-written from the edit (15,079).] So an
eviction costs one rewrite from the first edited row on, and nothing on turns with no
eviction. Unknowns: whether a mid-turn edit races Claude Code's own writes (evict only
between turns, under turn's lock), and whether a future version stops honouring an edited
transcript (turn-controls should assert that).

**Eviction mechanics.**
- **Batch, don't drip (Foil).** An eviction rewrites the cache from the first edited row to
  the end, and evicting the oldest units edits near the head, so each eviction costs close
  to a full-history cache write. So: evict rarely and in batches, at a boundary colder than
  the 1h TTL, or when headroom forces it, never one unit per turn. Fetch-backs append at the
  tail and stay cheap. The ledger checks this: an eviction's cost is the next turn's
  `cache_write`.
- **How Claude Code writes the transcript** [measured, strace, 2.1.289, one `-p` turn]: it
  opens `<sid>.jsonl` by path for each write batch (`O_APPEND`, plus one `O_CREAT|O_EXCL`
  at creation), never renames it, and a 1s fd sampler over a 10s turn never saw it held
  open. So writing a temp file and renaming it over the transcript is safe from a writer
  holding the old inode, and the remaining hazard is a **lost update**: a writer that opens
  the path just before the rename and writes just after it lands in the old, unlinked file.
- **Rule:** L2 transcripts are only ever resumed via turn, under turn's lock; check
  enforces it. An interactive `claude --resume`, or check's own probe until #46, bypasses
  the lock.
- **Lost-update detector, for whatever bypasses the rule (Foil, plus Ash).** turn is one
  process per turn, so it can't hold an fd across turns. Instead the editor hard-links the
  original to `<sid>.jsonl.pre-evict-<ts>` (0600, same directory) before the rename,
  records the size it read, and compares the link's size twice: right after the rename,
  and at the start of the next turn under turn's lock, before `--resume`. Claude only
  appends, so growth means a write was lost: fail loudly, then re-run the eviction from the
  current file. The link is deleted only after the **next-turn** check passes: a late writer
  that opened before the rename may not have written yet at the first check, so deleting
  then would leave the second check with nothing to compare (Foil). A **missing** link
  fails loudly; it never counts as "no growth", because a deleted link and an untouched
  one are otherwise indistinguishable (Ash). Scope: the tenant owns the directory and can
  delete or replace the link, so this is an accident detector, not tenant-proof. **Who
  deletes a link whose session never takes another turn (Wren):** the next-turn check is
  the only thing that removes a link, and §3.2 already contemplates that path — Refsdal's
  attack 8 counts cold-boundary evictions whose shorter prefix is never reused, the same
  no-next-turn case seen from the cost side rather than the artifact side. On it the link,
  and with it the full pre-eviction transcript, persists with nothing sweeping it. **This
  section proposes** (none of it exists yet) a **startup sweep** in turn: delete any
  `*.pre-evict-*` link whose session has been idle longer than a **sweep age** — a new
  quantity, hours-to-days, deliberately *not* §3.2's cold boundary, which is a
  cache-expiry condition (over an hour on Buster per §3.3's `ephemeral_1h` finding, 5
  minutes where the default TTL applies). A link one boundary cold is probably about to be
  checked; one idle a week is not. Log the deletion as an **unverified eviction, never a
  pass**: the second comparison never ran, so the lost-update question stays open for that
  eviction instead of being silently closed. This matters most in the headroom-forced
  case, which is also the case most likely to be followed by the session going cold.
  [measured on two hosts, ext4 and tmpfs: a hard link keeps the pre-eviction inode's
  blocks allocated, so until the link is deleted eviction reclaims nothing and in fact
  **costs** the size of the new prefix — a 4 MiB transcript evicted to 64 KiB left
  `sess.jsonl` at 64 KiB on a new inode and the link at 4,096 KiB on the old one, with
  free space 64 KiB *lower* than before the eviction; deleting the link returned 4,096
  KiB. Noise control on the shared filesystem (write 4 MiB, delete, measure drift) was +0
  KiB, so the 64 KiB exceeds the noise. The link's cost is
  exactly the bytes eviction set out to drop.] [measured, local simulation of the race: a
  clean eviction leaves the link at the read size (16 bytes, no fire); a writer that opened
  the path before the rename and wrote after it grew the link to 24 bytes (fired), and the
  new transcript lacked that write, so the loss was real and caught.]
- **Integrity on resume (Wren, as a turn-control assertion, not a note).** Anything that
  can write `<sid>.jsonl` can change what the model believes it was told. turn records the
  transcript's hash after each turn and each eviction, and refuses to `--resume` on a
  mismatch. Scope: an **accident detector, not tenant-proof** (Foil). turn runs as the
  tenant, who can rewrite the hash along with the `.jsonl`, so this catches writers that
  bypass turn (an interactive resume, a stray probe) and is not custody of the transcript.

Open items from Foil's review, not decided here:
- **C2a, a prefix-stability invariant.** L2's same-session cache_read share must be at
  least M1's, tested from the ledger. Anything that changes per turn goes after the stable
  part.
- **C3, the hard limit: DECIDED.** Will, 2026-10-07, on keeping Claude Code's compaction
  as a counted fallback rather than switching it off: *"Agree with your recommendation."*
  So Claude Code's compaction is **not** blocked or disabled anywhere in L2. It fires only
  if Hearth's manager has let the context reach the window, and each firing is an L2 miss.
  Reason: with it off, a long agentic turn that reaches the context limit fails mid-work
  and loses that work (the docs say the same of a PreCompact block at the hard limit, so a
  "proactive-only" block is ruled out too). A counted fallback is visible and recoverable.
  Wren adds: a miss must be **loud in the artefact**, not only in the log. turn prints it
  in its result line, and check reports the count.
- **C4, what turn pins, and the counter that must be able to fail.** turn's `--settings`
  carries three things the tenant can't override, because a tenant `settings.json` `env`
  replaces the process env (measured on #48):
  1. **The fallback window, pinned at 200,000 tokens** (`CLAUDE_CODE_AUTO_COMPACT_WINDOW`
     in the `--settings` env block). Why 200k: it is the trigger already measured to work
     on Hermes (L0), it sits far below Sonnet 5.5's ~967k default, so a miss is cheap, and
     L2's own budget must sit below it (target: evict by 150k) so the fallback fires only
     when L2 fell behind. The counter probe uses the same 200,000. The 100,000 in the probe
     above was only for speed and isn't a production value.
  2. **The PostCompact counting hook**, which writes one ledger event per firing.
  3. **`disableAllHooks: false`**, since a tenant's `disableAllHooks: true` would silently
     zero the miss count. Whether `--settings` wins over a tenant's `true` is
     **unmeasured**; turn-controls must test it.

  The counter must be able to fail: a turn-controls arm drives a session past 200,000
  tokens with L2 eviction off and must show a nonzero PostCompact count on the ledger. The
  negative control (stay under the window) must show zero.
- **Session identity.** M4's cost gate compares per conversation; with `--resume` kept, the
  Claude Code session id still serves.

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

**Measured input (miss-attribution study, `hearth-notes/miss-attribution/`, rule rev 12
e4d2c2dd, 2026-10-05).** Every noticed recall miss kept for pass 1 (5 of 5, after two
pre-registered exclusions; blind second labeller agreed 6 of 7 before them) was **S**: the
answer existed in this agent's own store, in *another of its own sessions*, but outside the
default search scope. All 7 candidate rows came from Ash's store alone, and both exclusions
were flagged during labelling under the pre-registered criteria (Foil C5). None was a ranking failure (R = 0), so M6 has no decision. Caveats:
n = 5, noticed misses only, and 5/5 is partly an artefact of excluding the disputed row.
Consequence for priority: widen scope before improving ranking. That means this section's
nightly consolidation, or a default cross-session search, comes before M6's retriever.
Pass 2 (≈2026-10-12) tests whether the pattern holds.

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

**Whoever observes a supersession can record it (Refsdal).** Not only the author of the old
decision. The evidence is ours: every crossed message on hearth#22 and #33 was one Ash
conversation acting on a pin that another Ash conversation had already replaced. The one that
saw the replacement must be able to write the link, or the stale pin keeps getting recalled.

### 4.3 A prefrontal gate on recall

[proposal] Recall is matched to the current *task* (open intentions + this turn), and a
relevance threshold drops what doesn't clear it, rather than injecting the top k with a LOW
label. Measurement: the tokens injected per turn, and how often an injected fact is
actually cited in the reply.

## 5. What Buster gets, in order (each a red-to-green, each measured)

1. **M0, ledger only (now):** memory ABSENT. The baseline cost per turn and the compaction
   rate at Claude Code defaults.
2. **M1, threshold (stopgap):** set the window in turn's env against the M0 baseline, and
   log every Claude Code compaction via PostCompact so M4 has something to beat.
3. **M2, hippocampus:** an index over Buster's transcripts (session, turn, identifiers) and
   a `recall` tool that returns verbatim lines by pointer. No summaries yet.
4. **M3, cortex:** Tapestry facts, written only by the nightly consolidation, each with a
   citation.
5. **M4, forgetting (replaces Claude Code's compaction):** Hearth builds each prompt from
   its own transcript store by §3.2 (L2 in §3.3), with eviction + fetch-back logging.
   Claude Code's compaction stays on as a counted in-turn fallback (C3).
   Gate: same or better on the §6 continuity quiz than the M1 logs, at no more ledger cost.
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
   - **Status after Foil's attack (reviews/41-foil.md @ 46065b77): NOT YET. Accepted.**
     1. *Too few labels.* Foil's 309 peer handoffs (09-30 to 10-04) hold 70 correction-like
        matches, mostly review findings or stale world state that re-fetching fixes. Foil
        found zero cases where the answer sat in its searchable store and ranking missed it.
        That's "zero to a handful in four days": eval data, not training data. (Ash's own
        regex count on his fact store, 422 of 613, measured how loose the regex was, not
        how often he's corrected.)
     2. *A miss has four causes:* never written, out of scope (e.g. only in another
        session), no query issued, ranked out. Only the last is trainable, and A1's blind
        spot is mostly "no query issued", so M6 could help only prefetch.
     3. *Wrong baseline.* Tapestry's ASSOCIATION.md is already a per-mind, use-strengthened
        cue-to-memory layer. M6 must beat the shared retriever **plus** associations.
     4. *The gate couldn't go red.* With #21 and the quiz not built, there are no positives.
        (Ash has the history: state.db from 2026-08-30, 262 sessions; facts from 2026-08-31,
        614. Foil's starts 09-30.)
     5. *Peer corrections are claims, not truth,* so one becomes a label only if its pointer
        resolves.
   - **So, in order:** (a) hand-label existing misses by cause (~1 hour on Ash's logs). This
     is the next real step, and it may move effort from retrieval to writing or scope;
     Step (a) gets a **fifth cause** (Refsdal): **U, retrieved but superseded.** The
     memory was found and ranked fine, but it was the old version. That's Refsdal's
     dominant failure. Better ranking makes it *worse*, and the fix is §4.2, not M6.
     Step (a)'s decision rule is **pre-registered before labelling** (Refsdal): with k
     ranked-out misses, a replay can't resolve a recall gain below ~1/√k (k=10 gives
     ~0.3). (Refinement: the SE is √(p(1−p)/k), so 1/√k is ~2σ only at p = ½, the worst
     case.) So three things are fixed in the labelling README before any row is read: the
     baseline recall on the R rows (expected near 0, re-run before any candidate), the
     minimum k (10), and the gain bar. Near p = 0 the decision is an exact paired test
     (McNemar), not the normal approximation. Pre-registered with it (Refsdal, rev 2, before
     any row): α = 0.05 one-sided; at k < 20 McNemar is what decides (b ≥ 5 discordant
     wins needed, i.e. an effective bar of 5/k); a **net test over all week-4 queries** (exact
     paired McNemar that overall recall improves; a non-inferiority margin was withdrawn as
     too loose: with R a small share of queries, a small per-query loss on everything else
     outweighs a large gain on R), so a candidate can't win by trading old hits for new; all
     tests must pass (intersection-union, deliberately no OR); and the deciding rows
     are disjoint from anything trained or tuned on.
     (b) keep the week-4 replay as an **evaluation** of today's retriever plus associations,
     read as an **optimistic bound**: it sees only queries that were actually issued, so it
     flatters every candidate (Refsdal, REV 2 (B));
     (c) build M6 only if (a) shows enough "ranked out" misses. If it's built, a **reranker**
     rather than an embedder: no re-index, and switching it off rolls it back.

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
