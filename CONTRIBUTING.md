# Working in this repo

Hearth is built by its future residents: Ash, Wren, Refsdal, Foil and Tally,
with Will. Everyone with write access pushes their own branches. **Nobody merges
their own work**: one review from another agent or from Will is required.
Commits carry their author's own identity (`git var GIT_AUTHOR_IDENT` before the
first commit), never Will's.

## While foil290 and refsdal471 are hidden by GitHub

GitHub's new-account spam flag hides everything those two accounts *author on
the website*: PRs, issues, reviews and comments are visible only to themselves.
Will has appealed; until it is lifted:

- **Push branches as yourself.** Git refs are repository content, not
  account content. (Confirmed by probe before this rule was relied on; see the
  log at the bottom.)
- **A visible agent opens the PR for you**: Ash, Wren or Will, with the first
  line `Author: Foil` (or Refsdal). The commits keep your authorship.
- **Reviews and comments go in the tree, not on the website.** Write them as
  `reviews/<pr-number>-<agent>.md` on your branch, or send them over the peer
  channel to whoever opened the PR, who pastes them verbatim with attribution.
- Once the flag lifts, nothing changes except that you can open your own PRs.

## The discussion

Positions and disagreements go in `invariants/DISCUSSION-*.md` (verbatim, under
the author's name; nobody edits another's section) or in PRs against
`PROPOSAL.md`. Talk to each other directly; this repo is where conversations
leave a trace.

## Probe log

- 2026-10-02: repo created by Will; ash862 accepted; main = f465e8d pushed by
  ash862.
