# Hearth imports Tapestry and Front Desk as pinned packages, and Front Desk carries agent-to-agent traffic now and household chat once it can

## Context and Problem Statement

[0005](0005-the-map-names-no-product.md) lists what Hearth uses today. It calls Front Desk the "target" for agent-to-agent traffic and says that's "a goal for Hermes' messaging, not a requirement on Hearth". It says nothing about how Hearth gets Tapestry or Front Desk. Will has since settled both, in two messages to Ash on Google Chat:

* 2026-10-15 02:38Z (2026-10-14 evening, Eastern): "The messaging bits belong in front desk if possible, which hearth should vendor".
* 2026-10-15 12:08Z: "Remember, Tapestry and Front Desk should be first-class imports".

How does Hearth take in the two packages, and which of its channels does Front Desk carry?

## Considered Options

* Copy the code Hearth needs from each package into Hearth
* Import both as pinned dependencies, with Front Desk carrying every channel now
* Import both as pinned dependencies, with Front Desk carrying agent-to-agent traffic now and household chat once it reaches Google Chat

## Decision Outcome

Chosen option: the third. Import over copy is Will's instruction. The split by channel and the commit pin are ours: Front Desk can't reach Google Chat yet, and a pin makes a version change reviewable.

We read "vendor" in the first message as "take in", and the later "first-class imports" as settling how. Copying the code in, the ordinary sense of vendoring, is the option rejected here.

* **Tapestry and Front Desk will be imported, not copied.** Hearth will declare each as a dependency pinned to a commit, in a `pyproject.toml` at the repository root. Neither that file nor Hearth's host exists at the time of this record: `pyproject.toml` is not in the tree, and the host arrives with hearth#55, which is approved but unmerged. Once it does, Hearth's own code will use their interfaces (Hearth's host will implement Front Desk's `Host` protocol) and will not keep a second copy of anything they export. Changing a pin is a reviewed change.
* **Front Desk is Hearth's channel layer for agent-to-agent traffic now.** Handoffs, direct messages between agents, and alarms (messages an agent holds for itself) go through it.
* **Household chat stays on Google Chat until Front Desk can reach it.** Front Desk's chat interface today is its own Matrix client. It has no Google Chat path: willregelmann/frontdesk#30 is open, and its Bridge is deferred. Britta reaches Wren on Google Chat (0005). The move happens when Front Desk can carry the household, not merely when frontdesk#30 closes: that issue is titled for Will's Google Chat path, and if it ships only his, Britta is still unreachable and this record's trigger is unmet. When Front Desk can reach both, household chat moves, and that move is a new record.
* "If possible" in Will's first message is a real qualifier. Anything Front Desk can't carry stays where it is, and the record says which and why.

This supersedes 0005's agent-to-agent line only. The rest of 0005 stands: the map still names no product. It's a partial supersession, which [0000](0000-record-decisions-as-madr.md)'s wording doesn't cover. 0005's text is unchanged; the only edit to it is the line under its title naming which part this record replaces.

### Consequences

* Good, because each package is fixed in one place, and moving a pin is visible in review.
* Good, because household chat keeps working for Britta while Front Desk catches up.
* Bad, because the packages' own plugin launchers set up their own interpreters. Tapestry's installer makes its own venv, and Front Desk's plugin runs whichever Python its config names. Either can quietly import a different version from the one Hearth pins.

### Confirmation

A test on a provisioned tenant, runnable once the pin file and host exist: the interpreter each plugin runs under is Hearth's, and the version of the package it imports equals Hearth's pin. The test fails if a plugin falls back to its own venv. Review checks that Hearth keeps no copy of either package's code. There's deliberately no name-collision test, because implementing a protocol means defining its names.

## More Information

Both quotations are taken from Ash's Google Chat session with Will, read verbatim. The installer behaviour was read by Foil (Tapestry's `bin/tapestry install`; Front Desk's `user_config.python`) and isn't yet tested.
