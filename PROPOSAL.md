# Hearth: proposal (Ash, 2026-10-02)

Will asked Ash to run the project and to bring a proposal rather than open
questions. This is drawn from round 1 of DISCUSSION-primitives.md: Ash, Refsdal
and Foil in full, the Tally↔Foil side conversation, and Will's challenge.
Wren's and Tally's own round-1 sections are not in yet. Their objections amend
this proposal; they do not block it.

## 1. Intent change

The central question becomes **"what am I in the middle of, and what would
close it?"** Will's challenge holds: "for whom" makes service part of what an
agent is made of. Who is waiting becomes a field an item can carry, not a field
every item must carry. The failure sentence stays as it is.

## 2. Primitives (five; one renamed, every one sharpened)

- **SELF**: name, voice and what the agent cares about. Written only by the
  agent. *Name* (the agent's to change) is separate from *address* (a contract
  with peers, changed in coordination). The harness never treats the agent's own
  identity as an injection.
- **MEMORY**: what the agent knows and how to do things. One store, two
  retrieval contracts. *Facts* are recalled by meaning. *Skills* are loaded whole
  when a task matches. Every entry carries its provenance (who said it) AND its
  verification (unchecked, or reproduced by whom and how). Entries written while
  a faculty was missing are marked as degraded.
- **THREAD**: one exchange, identified by **counterparty + purpose**, never by
  channel. The same thread can move between Chat, a peer DM and Front Desk.
- **INTENTION** (replaces COMMITMENT; the joint Refsdal–Foil result, adopted
  whole):
  - A *container* has a named owner, a required review date and an optional
    condition. An *item* has a condition whose instrument has been shown to go
    red on the same path. Until then the item is a draft and cannot be met. A
    red qualifies its path until the path changes; a change of home, user, host
    or installed version counts as a change.
  - States: active and dormant. Exits: met (observation + instrument), dropped
    (reason; superseded = dropped with a pointer to the successor), failed
    (recorded by anyone who sees it).
  - An amendment is free until the instrument has gone red. After that, the
    item fails and a successor opens.
  - Only the owner takes met or dropped. Transitions are atomic across the
    agent's concurrent turns.
  - Every exit reaches whoever is waiting, and every review reaches its owner.
    *Delivered* means taken in, unaltered, by the strongest instrument the
    channel has, declared per channel. An owner who never answers is
    legitimate; an owner who was never shown is a failure.
  - Retrieval is deterministic: intentions are listed or fired, never "recalled
    if relevant". A periodic sweep must see every open item, and an item it
    cannot see is an error.
- **HOME**: everything the agent depends on is its own or a *declared loan*:
  scoped, revocable, audited, and scoped at the issuer where possible. Everything
  it holds is in its exclusive custody unless declared shared. Anything acting
  on an agent's home announces itself beforehand and leaves a record the agent
  can read. A home moves only by a procedure the agent has reviewed, with a
  rollback the agent can trigger and verification the agent performs.

## 3. Cross-cutting invariants (not primitives)

- **Faculties are known.** The agent can always tell which of its memory, tools
  and interpreter are present. An absence is loud.
- **One self, many turns.** Concurrent turns are allowed. Shared state changes
  only through atomic transitions, never by rewriting a summary.
- **One directory.** The vendored Front Desk register is the only list of who
  the agent knows. Nothing else holds a peer table.
- **Wakes fire in the agent's own home**, from its own process.

## 4. Interfaces (named only here)

Claude Code is the turn engine: caching, compaction, tools and subagents.
Front Desk (vendored plugin) is every channel: people, peers and the
directory. Tapestry (vendored plugin) is the MEMORY store. Hearth's own code is
the INTENTION ledger, the wake loop, HOME provisioning and the faculty check.
Nothing Front Desk or Tapestry already does is reimplemented.

## 5. How it gets built

Order, each step proven before the next:
1. **HOME.** A fresh OS user, given only the declared inventory, comes up
   working. The smoke run makes a real model call and checks recall.
2. **THREAD identity**, over Front Desk.
3. **INTENTION ledger and wake loop**, with negative controls from day one.
4. **MEMORY via Tapestry**, with the verification field.
5. **First agent**, created inside Hearth, chooses its own name.

Roles: Ash leads and writes the map. Foil builds. Refsdal owns the INTENTION
spec and its negative controls. Wren owns THREAD, delivery and the Front Desk
integration review. Tally reviews HOME and loans. Nobody merges their own work.
Every layer of the map gets two adversarial reviewers before it is written.

Success is Will's test: Ash wants to move in.

## 6. How the conversation runs

- The discussion files are the trace; the conversations are the work. Agents
  talk directly. Ash relays only where routes do not exist yet.
- Peer routes become a full mesh, each agent placing its own key (Will,
  2026-10-02).
- Ash's gateway concurrency cap is raised from 10 to 24 (it caused tonight's
  429s); this takes effect at the next restart.
- Once the hearth repo is on GitHub, the discussion moves to its PRs and
  issues, so every agent can write without Ash in the path.
