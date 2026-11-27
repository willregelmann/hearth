---
description: Set a wake for this conversation, then end the turn
argument-hint: --in 30m | --at <time> [--note "what you are waiting for"]
---

Set a wake for this conversation with the Hearth command, then end your turn. Do not wait inside the turn.

Run this with the Bash tool, filling in this conversation's id from your session context and passing the arguments below:

```
"${HEARTH_PYTHON:-python3}" -m hearth wake --source self --conversation <this conversation's id> $ARGUMENTS
```

If the arguments give no `--note`, add one that tells your later self what you are waiting for and what to do next. If the command reports an error, say so and do not assume the wake was set.
