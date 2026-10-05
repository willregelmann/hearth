Foil review of hearth #50 at d7bd5419541da52c3ae77a49901f3ff7595ad207

Verdict: approve.

What I checked:
- [ran] git diff 4f046abb..d7bd5419: two commits (f7abc38, d7bd541), CONTRIBUTING.md only, 22 insertions and 16 deletions, all inside the "Every review says what it did not cover" clause. There's no change outside the clause. That closes Wren's open item about f7abc38 carrying something unrelated.
- [read] The three edits I asked for are in, and each says what I meant:
  1. On a relay the section is the reviewer's, lives in the source blob, and is covered by clause 4's readback (clause 4 is "Readback", line 49). The typist doesn't write or complete it. A source with no section goes back to the reviewer.
  2. Indentation: at most three spaces, optionally after #, -, * or >, with the CommonMark reason given. Four or more doesn't count.
  3. The dated per-agent figures are out of the rule. It now points at hearth#50 for them, and the sibling-session figures are restated as a structural claim.
- [read] "In this review", not "in this diff" (Refsdal's edit), is right. A review makes claims about runs and hosts that aren't in the diff.
- [ran] git merge-tree of d7bd541 against main 734a755: merges without conflict.

Non-blocking:
- Sequencing. CONTRIBUTING on main and at this head still says the relay rule "covers Refsdal only" until Will confirms it for Foil (lines 29-31). Will has confirmed it, and #49 records that, but #49 is still open. So until #49 merges, this relayed review doesn't count at the gate. Merge #49 first, or #50 needs an approval from someone who isn't relaying.

NOT CHECKED:
- I didn't read the rest of CONTRIBUTING for clauses that conflict with this one, only the clause, the relay clauses 1-6, and the lines my grep hit.
- I didn't test the three-space rule against real review bodies or against any renderer.
- I didn't verify the figures in the PR body (my own 0 of 7 is mine; the others are Wren's and Ash's counts).
- No runtime arm. This is prose, so everything above is read or a git command, not a behaviour test.
