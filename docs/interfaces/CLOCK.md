# Clock

Time, which is what makes a wake due, a retry come round and a check run again. On the other side is the machine's own clock.

## What passes

| Firing | What it does |
|---|---|
| Not-before time reached | Makes a [wake](../primitives/WAKE.md) due |
| Retry delay passed | Makes a conversation whose turn failed eligible for another turn |
| Check interval passed | Runs a [check](CHECKS.md) again |

## Invariants

- **A wake never runs before its not-before time.**
- A firing that couldn't happen on time happens late rather than not at all, and a late wake says how late.
- A restart never fires a not-before wake early, and never loses one.
- The gateway reads time from one place, so that a test can replace it.
