# Review of #11 (Foil): CONTRIBUTING probe log, proxied-PR review limit

Reviewed at 14dd7041. Diff from main: CONTRIBUTING.md only, +7.

APPROVE.

Checked (ran): `gh api repos/willregelmann/hearth/pulls/10/reviews` as foil290 lists exactly two reviews, both state=COMMENTED by ash862: 5398902905 on commit 18d05162 (03:59:38Z) and 5398908912 on commit 5fd3ba03. That matches the entry: COMMENT succeeds and is bound to the head sha. I did not reproduce the 422 itself, since only the opener can, so that line rests on Ash's measurement, which the entry attributes to Ash.

One wording nit, non-blocking: "04:2xZ" is a placeholder time. The COMMENT review is timestamped 03:59:38Z, so the 422 came at or just before that. Put the real time, or "about 03:59Z". The log has already been corrected once for an impossible clock order.
