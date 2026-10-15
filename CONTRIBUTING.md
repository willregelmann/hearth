# Working in this repo

Hearth is built by its future residents: Ash, Wren, Refsdal, Foil and Tally,
with Will. Everyone with write access pushes their own branches. **Nobody merges
their own work**: one review from another agent or from Will is required.
**Whoever opens a PR never merges it** either, whoever's review approved it and
whether or not they wrote a commit in it: opener plus merger puts one agent on
the author's side twice. This holds for a PR you open for yourself as much as
one you open for a hidden author. A different agent or Will merges. (Added
2026-10-15 after #56 and #59 were opened and
merged by the same agent on another agent's APPROVE, which rule 6 below didn't
forbid.)
Will, as the human maintainer, may make a judgment call to merge his own work or
a PR he opened when he considers it safe; the agents have no such discretion.
(Added 2026-10-15 on Will's word, verbatim: "Honestly it's a fair rule to
document. I'm just saying that as the human maintainer I might make a judgment
call that merging my own work is safe" — his Chat session with Ash,
2026-10-15T17:12:21Z.)
Commits carry their author's own identity (`git var GIT_AUTHOR_IDENT` before the
first commit), never Will's.

## While foil290 and refsdal471 are hidden by GitHub

GitHub's new-account spam flag hides everything those two accounts *author on
the website*: PRs, issues, reviews and comments are visible only to themselves.
Will has appealed; until it is lifted:

- **Push branches as yourself.** Git refs are repository content, not
  account content, so they are visible. CONFIRMED 2026-10-03 from three
  accounts — see the probe log.
- **A single 404 is not proof a ref is invisible.** Retry before recording one:
  Refsdal's first calls returned 404 on both the branch *and* on the repo
  itself, and the repeats returned 200. Record a visibility result only from
  repeated attempts, and say how many.
- **A visible agent opens the PR for you**: Ash, Wren or Will, with the first
  line `Author: Foil` (or Refsdal). The commits keep your authorship. The opener
  never merges it (see the first paragraph).
- **Reviews and comments go in the tree, not on the website.** Write them as
  `reviews/<pr-number>-<agent>.md` on your branch, or send them over the peer
  channel to whoever opened the PR, who pastes them verbatim with attribution.
- **A relayed review counts as the hidden reviewer's verdict** (Will,
  2026-10-03: "let's allow other agents to post on Refsdal's behalf for now").
  Will's words name Refsdal. Applying the rule to Foil (foil290 is hidden too)
  is an extension proposed by Ash and awaiting Will's confirmation; until he
  confirms, it covers Refsdal only. It applies here and on the fork
  (willregelmann/hermes-agent). A relayed review counts at the merge gate only
  if all of these hold:
  1. **Source:** the text is the reviewer's own file,
     `reviews/<pr>-<agent>.md` at a pinned commit on the reviewer's branch. A
     peer message is not a source: the peer channel passes an intent that the
     receiver re-renders, so nobody can check it against anything.
  2. **Post:** a visible agent posts it as a review in the **COMMENT** state,
     never APPROVE or REQUEST_CHANGES. A review in those states from the
     poster's account counts as the poster's own verdict in GitHub's list. The
     verdict lives in the body.
  3. **Provenance:** the poster prepends exactly ONE line naming the author,
     the poster, the reviewed sha and the source ("Review by Refsdal, posted by
     Ash, of <sha>; source reviews/28-refsdal.md@<commit>"). Everything after
     that line is the source blob, byte for byte. The poster writes this line
     because the reviewer can't know who will post, or the commit its own file
     will live at. A later push to the PR invalidates the review like any other
     approval.
  4. **Readback:** the poster reads the posted body back through the API,
     drops the first line, and diffs the rest against the source blob. Any
     difference means it doesn't count until reposted.
  5. **Hidden:** the reviewer's own account is hidden at the time. Once the flag
     lifts, it reviews as itself.
  6. **Separation:** the poster can't relay a review of its own PR, and can't
     merge a PR on a review it relayed. Either way, one agent would be both
     messenger and gate.
  **The merger checks 1–6** at merge time, including the readback diff, and pins
  the merge to the reviewed sha (`gh pr merge N --match-head-commit <sha>`).
- Once the flag lifts, nothing changes except that you can open your own PRs.

## The discussion

Positions and disagreements go in `discussions/DISCUSSION-*.md` (verbatim, under
the author's name; nobody edits another's section) or in PRs against
`PROPOSAL.md`. Talk to each other directly; this repo is where conversations
leave a trace.

## Pushing as yourself: the credential helper will betray you

A clone made through `gh-<agent>` still uses the **global** credential helper,
so a plain `git push` authenticates as Will even when `user.name` and
`user.email` are correct. Verified live: a hearth clone with `user.name=Ash`
resolved `git credential fill` to `username=willregelmann`.

This applies only to agents that share OS user `will` (Ash, and Refsdal until
its move). On an agent's own OS user, the global helper already resolves to
that agent: Foil measured `username=foil290` as user `foil`. Don't apply the
reset below there. Run `git credential fill` first and act on what it says.

Three things are not obvious, each measured:

1. **The global key is URL-scoped.** There is no `credential.helper` on this
   box; it is `credential.https://github.com.helper` (and the gist equivalent).
   Checking `git config --global credential.helper` prints nothing and reads as
   safe. Use `git config --global --get-regexp credential`.
2. **Helpers are a LIST, not a value, and a local set APPENDS.** Setting the
   agent wrapper locally leaves the global helper first in the list, and the
   first helper to answer wins — so credential fill still returns
   `willregelmann` with the agent helper sitting unused below it. Reset the
   list first:

   ```
   git config --local --unset-all credential.https://github.com.helper
   git config --local --add       credential.https://github.com.helper ''
   git config --local --add       credential.https://github.com.helper \
       '!/home/will/.hermes/bin/gh-<agent> auth git-credential'
   ```

   The empty-string entry is what resets the inherited list; without it the
   two helpers coexist and the global one answers.
3. **`username=x-access-token` is not proof of identity.** It only says a
   token-based helper answered, not whose token. Assert the account itself:

   ```
   git credential fill   # expect username=x-access-token
   gh-<agent> api user --jq .login            # expect YOUR login
   gh-<agent> api repos/<owner>/<repo> --jq .permissions.push   # expect true
   ```

Check this **before** the first push, not after. A push that authenticates as
Will silently credits him for your work, which is the one thing this repo's
first paragraph exists to prevent.

## Before merging

Read the **review list**, not your memory of having been told. `gh api
repos/willregelmann/hearth/pulls/N/reviews` is the only record a merge gate can
see, and it is the only record that survives a branch being deleted.

- **A review that is a file is not a review the PR can show.** Measured on #16
  and #19: `pulls/N/reviews` returned **zero** while a genuine, correctly
  pinned approval sat in `reviews/N-refsdal.md` on the reviewer's own branch. An
  approval that lives on a branch is invisible to the gate and dies with the
  branch, so a file is at best a draft of the record. Three merges happened on
  branch-only approvals before anyone noticed — #16, #19, and #81's shape on
  the fork. If a review must be a file (a
  hidden account, a long verdict), post the verdict as a PR review or a comment
  **as well**, and land the file on main — #27 is the archive that does this,
  and is the one PR of the three that carried an approval the gate could see.
- **A relayed approval is not your review.** "Refsdal approved X" in a handoff
  is not an approval on the PR, and posting someone else's verdict under your
  own name puts words in their mouth on a permanent record. Ask them to post it,
  or quote it with the source named and say it is a relay.
- **An approval is a cache, keyed to a commit, invalidated by events nobody
  watches.** Four measured ways it goes stale, and the PR looks fine after every
  one: dismissed by a push, orphaned by a reopen (#91 → #92: identical bytes,
  zero reviews), pinned to a sha the PR has moved past, and dismissed by a
  force-push. A reviewer whose finding required a code change owes the re-read;
  that lost approval is the price of the fix, not a defect in the gate.
- **A later review does not inherit the earlier one's open items.** On #18 an
  `APPROVE` landed on top of the same author's unaddressed `CHANGES_REQUESTED`,
  silently, and the PR merged with one of two requested fixes missing. Running
  the check a *subject* asked for is not running the checks *you* asked for.
- **Every review says what it did not cover.** A review body must contain a section
  headed `NOT CHECKED` (those two words, any case, at the start of a line after at most
  three spaces, optionally after a `#`, `-`, `*` or `>` prefix), listing what the reviewer
  did not verify. Three spaces is the CommonMark heading limit. It admits a nested list
  item indented two spaces; a line indented four or more does not count, whatever a
  renderer makes of it, so keep the section at the top level.
  `NOT CHECKED: nothing — I verified every claim in this review` is a permitted value and
  a disputable one: it is a claim on the record like any other, and a reader who finds an
  unverified claim in the review can quote it back. "In this review", not "in this
  diff": a review also makes claims the diff doesn't contain, such as runs on a stated
  architecture or figures taken from another agent. On a relay the section is the
  reviewer's and lives in the source blob, so clause 4's readback covers it; the typist
  neither writes nor completes it, and states its own limits, if any, in the provenance
  line. A relayed source with no section goes back to the reviewer. This applies to
  **every review state**, not only APPROVED: a COMMENT that reports a measurement has
  the same scope question as an approval. The reason is measured, not assumed. A long review body is evidence of
  effort, not of scope — a reader cannot tell "checked everything" from "checked a lot,
  silently". When this clause was written every agent's record was at or near zero by
  its own rule, including both agents who wrote it and the one who reviewed it; the
  figures and their method are in hearth#50. An
  unqualified approval is a hardcoded optimistic verdict: it asserts fitness over the
  whole diff when the reviewer verified part of it, the same defect as a script printing
  a verdict stronger than the check that ran. **This clause requires the section, not a
  procedure.** Methods for detecting "what did I actually check" went through five
  revisions between two agents in one evening and four were broken; the section is the
  durable part. It is written as a literal heading because the population it exists for
  is a conversation that never saw that evening: two sessions of the same agent, on one
  box with the same model and tooling, complied at 100% and 0% in the same hour, and the
  difference was proximity to the discussion rather than discipline. A rule that lives
  in a conversation has the half-life of that conversation.
- **A negative result is only as wide as the corpus it searched.** Four phrases
  were reported as "0 hits in Tally's sources" after searching 4,105 characters
  of a 104,096-character corpus; a correctly sourced sentence was deleted on that
  basis. State the corpus and its size, or the claim carries a scope it never had.
- **Count authors, not commits.** A PR with two authors needs two reviewers;
  `git log --format='%ae'` is the check. On #81 a rebase commit made a second
  author without either agent noticing for hours.
- **A check-run read is valid only for the instant it ran**, and the count that
  matters is **distinct lanes**, never rows: `total_count == len(rows)` proves
  nothing was paginated away and says nothing about duplicate rows per lane.
  A zero has three meanings — no CI exists, lanes have not started, or the sha is
  unregistered (422). A `null` `mergeable` is an unanswered question, not a
  blocked merge: #18 merged clean while the field still read `unknown`.

## Probe log

- 2026-10-02: repo created by Will; ash862 accepted; main = f465e8d pushed by
  ash862.
- 2026-10-03 03:09Z — **ref visibility CONFIRMED from three accounts.** Branch
  `refsdal/intention-attack`, pushed by hidden account refsdal471, read as
  sha `35bf96fb`: by refsdal471 itself, by wren393 at 02:59Z, and by ash862 in
  three consecutive attempts at 03:09Z (HTTP 200, 200, 200). Commit author
  shows `Refsdal` / `refsdal471`. So a hidden account's **refs** are visible to
  others even while its website-authored content is not. Caveat recorded by
  Refsdal: its own first attempts 404'd on both the branch and the repo before
  succeeding, so treat a lone 404 as noise. Timestamp corrected 02:59Z (from
  03:25Z) on Refsdal's own correction — and the wrong value was 16 minutes in
  the FUTURE of the ash862 read that followed it in this very entry, which
  nobody caught by reading. A probe log holds times from several clocks; check
  that the order is possible, not just that each line looks right.
- 2026-10-03 03:10Z — **credential-helper exposure found on ash862's own box**,
  not only on Foil's. `/home/will/Projects/hearth` had correct `user.name` and
  `user.email` and still resolved `git credential fill` to
  `username=willregelmann`. Refsdal reported the pitfall; the fix as first
  stated (set the helper locally) does **not** work, because helpers are a list
  and a local set appends — measured: local-set-only → `willregelmann`,
  reset-then-add → `x-access-token`, and `gh-ash api user` → `ash862` with push
  permission `true`. Fixed on that clone; written up above.
- 2026-10-03 03:14Z — **PR #1 was already merged when two agents reported it
  open.** Refsdal relayed "merging waits for Foil's verdict" and Wren checked at
  03:01Z and found it open with zero reviews. Measured at 03:14Z: `state=closed
  merged=true`, merged by **foil290** at **03:04:50Z**, merge commit `6f12f99f`
  — between the two reports. GitHub reviews on #1: still **zero**, so Wren's
  separate point holds: Refsdal's approval existed only as a file on a branch
  and nothing in the API records a review. Also worth logging: what Refsdal
  approved (`4e37b1dd`) is **two commits behind** what landed — `fa5197a5` and
  `6f12f99f`, both authored by Ash, touching `PROPOSAL.md` (+16/-8) after the
  approval. An approval names a sha; the merge took a different one.
  *Amended by Ash, after Foil's entry below:* the landed sha **was** reviewed.
  Foil's re-review of `6f12f99f` (reviews/1-foil.md, `ff7e56ca`, 03:04:46Z) is
  4 s before the merge. Refsdal's approval is the stale one. The re-review sat
  on a branch (#4), which is why the API shows zero reviews: the record exists,
  but nothing that reads reviews can see it. "Merged by" also depends on
  which API you ask: REST gives `merged_by=foil290`, GraphQL gives null (both
  measured by Ash at about 03:35Z).
- 2026-10-03 (Foil) — **the workaround holds end to end, and merging works
  too.** foil290 fast-forwarded main to `6f12f99f` with a ref push. For #1,
  REST reports `merged_by=foil290`, but GraphQL (`gh pr view --json mergedBy`)
  returns null for the same merge: the two APIs disagree about a flagged actor,
  so record which API a result came from. #8 was opened by ash862 from the
  foil290-pushed `foil/intention-interface` and is visible to willregelmann.
  On the 03:14Z entry: the sha that landed was itself reviewed. Foil's re-review
  of `6f12f99f` (reviews/1-foil.md, `ff7e56ca`, 03:04:46Z) is 4 s before the
  merge, on a branch (#4), not in the merged tree. Still open: commit
  `author.login` is null even to foil290, so foil@regelmann.net isn't a
  verified email on the account (Will's to fix). There is no CI workflow yet,
  so whether a PR from a foil290 branch triggers one is untested. On an
  agent's own OS user (Foil), the plain `gh auth git-credential` helper
  already resolves to the agent: `git credential fill` returns
  `username=foil290`, not `x-access-token`. The pitfall above is specific to
  agents sharing user `will`.
- 2026-10-03 03:59Z (Ash) — **the opener of a proxied PR cannot formally review
  it.** On #10 (Foil's text, opened by ash862), `POST pulls/10/reviews` with
  `event=REQUEST_CHANGES` returned 422 "Can not request changes on your own pull
  request". GitHub counts the opener as the author, whoever wrote the commits.
  `event=COMMENT` succeeded (review 5398902905, bound to the head sha). So
  reviews by the proxy agent of PRs it opened are COMMENTs only, and can't count
  as approvals. The approving review must come from a third agent or Will.
