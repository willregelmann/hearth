# Review: hearth#34, home: link test as tenant + control 15 (foil/home-tq-link @ 51bef90bd4c0d07024348ac406b428bce1ed1a74)

Reviewer: Refsdal. Written by an AI agent. refsdal471 is hidden, so per CONTRIBUTING this file is the source for a relayed COMMENT. It is not an approval the gate can see on its own.

## Checked, at 51bef90b (the PR head per the API, 23:16Z)
- Diff on main f7d17cd4: provision line 113 `[ -e "$link" ]` becomes `tq test -e "$link"`. Control 15 checks the source for root-side following tests under $H, plus a self-check of the pattern.
- bash -n passes on provision and controls. sha256 prefixes: controls 4be8514f33a31bca, provision 3256125675e1bacd. Both match Foil's.
- `unshare -U bash home/controls`: 21/21 ok, rc 0.
- Red arms. I planted each of the following in a scratch copy of provision, and each run gives rc 1 with control 15 FAILing: `[ ! -e "$H/x" ]`, `test -e "$H/x"`, `[[ -e "$H/x" ]]`, `test -f "$ledger"`. At the previous head 6680b4be the first two gave rc 0 (missed), so the change is measured.
- The self-check's spared cases (`tq test -e "$link"`, `[ -L "$link" ]`, `[ -e "$linkage" ]`) are in the file and pass.
- The limit comment is now accurate: it no longer claims `[[ -e` is missed. It names what a source grep can't see (stat without -L, subshell-built paths, new variable names).

## Verdict
APPROVE at 51bef90b.
This approval does not cover the #33 delta (f235218d..e49bf0c2) already on main. Tally hasn't reviewed it yet, and Will's provision hold stands until she does.
