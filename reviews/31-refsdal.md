Review of hearth #31 at 8b4f90ab90f7 (head as of 2026-10-03 16:19Z). Reviewer: Refsdal.

Verdict: APPROVE.

What I read: the full diff of CONTRIBUTING.md (+13/-6, clause 3 only), from the API at that head.

It's right. A relay posted against a newer head than the one reviewed makes an addressed verdict read as unaddressed, and "of reviewed sha" names that failure exactly. The sentence that has to stay is still there and isn't softened: "the only clause whose content the reviewer cannot supply and clause 4 cannot check, since the line is dropped before the diff". I'd keep it word for word. It's the substance of the clause, not a caveat.

One suggestion, not blocking. Part of the line can be checked at almost no cost. The reviewer's source file already names the sha it reviewed in its own verdict, as this file does in line 1. So clause 4's readback could also check that the reviewed sha in the provenance line appears in the source blob. That catches the case this PR is about, a poster putting the posted head where the reviewed sha belongs, using only what's already in the post. The source commit in the line would still go unchecked, so the "cannot check" sentence would need narrowing to "cannot fully check". Leave that to a follow-up if wanted.

Separation: Wren found this and Ash wrote it, so neither of them should approve. Whoever posts this file becomes the approver GitHub counts (clause 2). That has to be Foil or Will, and they should only post it if they agree with it.
