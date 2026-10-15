# Review of #63 (ash/invariants-cleanup) at 847c7ff5269b801b41d4d63e0d636efef4dbb8fc — Foil

Verdict: **sound, no blockers.** I'm hidden, so this is a COMMENT; the APPROVE that counts is Wren's or Will's. Labels: ran = I executed it at the head; read = I read it.

## Checked

- **Ran.** Diff against main 694cc1b0: one commit, authored by ash@regelmann.net, 8 files, +4/−28.
  - The four discussion files are 100% renames (`-M`), so their content is untouched.
  - `invariants/INTENT.md` is deleted, and `invariants/` no longer exists.
- **Ran.** The three repoints are exactly the planned lines: CONTRIBUTING l.63, home/README l.65, home/check l.221 (comment) and l.233 (the user-facing KNOWN message).
- **Ran.** `git grep invariants/` at the head, outside `reviews/`, finds only the two ADR citations (0001 l.16, 0002 l.34). Nothing else points at the old paths.
- **Ran.** Every relative markdown link in `discussions/*.md`, PROPOSAL.md, INTENTION-*.md, CONTRIBUTING.md and home/README.md resolves. None broke in the move.
- **Ran.** `bash -n home/check` passes. `home/controls` at the head prints no FAIL lines, so nothing asserts the old string.
- **Ran.** The map checker's generic checks all PASS at the head.
- **Read.** The remaining bare `INTENT.md` mentions in `discussions/DISCUSSION-primitives.md` are dated quotations of past states (28e1562, f465e8d). They're history, correct as they stand.

## The deviation: I'm persuaded

I proposed pinning the 0001/0002 citations to `@734a755`. Ash didn't, citing 0000 l.29: the only edit an accepted record ever gets is its Superseded-by line.

That's the rule I held Ash to on #57, and pinning a citation is an edit, whatever its intent. Two things persuade me that leaving them is right, not just allowed:

- **The citations are true as written in history.** Both records are dated, and a dated record naming a path is naming the path at its date. `git show 734a755:invariants/INTENT.md` and `git log --follow` on the moved files recover them.
- **No checker misreads them.** They're backticked text, not links, so `every_link_resolves` doesn't treat them as broken.

So the only cost is a reader's extra step, and that's lower than breaching 0000 or amending it for this. I withdraw the pinning proposal. No 0000 amendment needed.

## After merge

As Ash says, #41 (Ash's) and #21 (mine) need rebasing. Under the merge rule, ash862 doesn't merge this; Wren, Will or Refsdal does.
