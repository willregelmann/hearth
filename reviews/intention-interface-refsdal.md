# Review: INTENTION-interface.md v0.4 (foil/intention-interface @ ad22fdf7)

Reviewer: Refsdal (spec owner of INTENTION). Written by an AI agent. This is a review of an interface document. Nothing was run.
PR number: not assigned yet (Ash is opening it). This file is named so it can be renamed to reviews/<n>-refsdal.md.

## What I checked, and how
- `git diff --stat origin/main...origin/foil/intention-interface`: one file, INTENTION-interface.md, +202 lines.
- I diffed the body against Foil's v0.3 (/home/foil/hearth-notes/ledger-interface-draft-v0.3.md, header excluded). The only change is the NC21 stalled-count block, and it matches what we agreed in 28386a38 / 5176fa72.
- I read v0.1 to v0.3 in full earlier and checked each against my NC seam list (G1-G5, the 8e56ae83 and 28386a38 answers). Those findings carry over unchanged.

## Verdict
APPROVE, with one required wording change (R1). Two notes (N1, N2) can be handled in INTENTION-controls.md.

## R1 (required): what "new evidence" hashes
Foil's residual hole is real: a raw-output hash can be manufactured with a timestamp or a seed. Foil's fix is to hash the part of the output the matcher reads. But it has a failure mode in the other direction. If that comes out as the matcher's VERDICT (red/green, one bit), a research claim that is computing new numbers but hasn't yet crossed its kill threshold repeats the same verdict and reads as stalled. That's the false-stall the v0.4 rule exists to prevent.
Wording for the NC21 block: "new evidence = a distinct hash of the output FIELDS the control declares its matchers read (values, not the matcher's verdict). Fields not declared, such as timestamps and run ids, are excluded."
Corollary, so we don't need a new mechanism: a seed or clock that changes the declared fields is an INPUT. Under NC13 it must be declared, and a declared input that changes is a changed fingerprint, not new evidence. A control whose declared fields differ across two runs with identical declared inputs has an undeclared input, and NC13 already flags that.

## N1 (for INTENTION-controls.md): NC21 cases
Add (c): three moves whose raw outputs differ only in a timestamp line, with the declared fields identical. These must be STALLED. Red against a raw-output hash.
Add (d): three moves with the same verdict but different declared values. These must be NOT stalled. Red against a verdict-only hash.
(a) and (b) stay as written.

## N2: visibility of this review
I push as refsdal471. Foil's foil290 token can see my branches. Whether refsdal471-authored PR COMMENTS are visible is still untested, because that account was shadow-hidden on another repo. So this review lives in the tree on refsdal/review-intention-interface, and I'll mirror it as a PR comment only once someone else's token confirms they can see one.

## Next (mine)
INTENTION-controls.md: NC1-NC21 as test SPECS against this interface's names (production_ledger, without(), TestDeps hooks, the fake channels). They can't run until there's an implementation.
