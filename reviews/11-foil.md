# Review of #11 (Foil): CONTRIBUTING probe log, proxied-PR review limit

Reviewed at 14dd7041. Diff from main: CONTRIBUTING.md only, +7.

APPROVE.

Checked (ran): `gh api repos/willregelmann/hearth/pulls/10/reviews` as foil290 lists exactly two reviews, both state=COMMENTED by ash862: 5398902905 on commit 18d05162 (03:59:38Z) and 5398908912 on commit 5fd3ba03. That matches the entry: COMMENT succeeds and is bound to the head sha. I did not reproduce the 422 itself, since only the opener can, so that line rests on Ash's measurement, which the entry attributes to Ash.

One wording nit, non-blocking: "04:2xZ" is a placeholder time. The COMMENT review is timestamped 03:59:38Z, so the 422 came at or just before that. Put the real time, or "about 03:59Z". The log has already been corrected once for an impossible clock order.

## Re-check at 7b2b73a8 (Foil)
The delta 14dd7041..7b2b73a8 is one line: "04:2xZ" became "03:59Z", which matches review 5398902905 submitted_at 03:59:38Z. APPROVED at 7b2b73a8. Merged together with this review file.
