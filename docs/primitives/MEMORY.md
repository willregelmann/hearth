# Memory

What the agent knows and how it does things, written by the agent itself. Facts and skills are both memory: a fact is something that holds about the world, and a skill is a way of doing a task, with the corrections that came from doing it. They can share a store, but they're reached differently. A fact is recalled by meaning. A skill is loaded whole when a task matches it.

Every memory carries two things beside its content: who it came from, and whether it has been checked. Who said it doesn't change. Whether it's been checked can: a peer's claim the agent hasn't reproduced is unchecked, and becomes checked when someone reproduces it, recorded with who and how.

## Invariants

- **Every memory says who it came from and whether it has been checked.** A recalled memory carries both, so the agent never passes off an unchecked claim as something it verified.
- **A skill is loaded whole.** Nothing serves part of a skill, and a skill is never buried among facts that merely look similar.
- A memory that's only loosely related is labelled that way when it's recalled. It's never presented as an answer.
- A memory written while one of the agent's [faculties](HOME.md) was missing is marked as written in that state.
- A correction is linked to what it corrects. Recall never returns a corrected memory as if it still stood.
- Recall that fails says it failed. The agent is never shown "nothing relevant" when its memory wasn't searched.
- An agent's claim that it never did, said or saw something names where it looked, truthfully, or says it didn't look.
- Each fact carries its audience as part of where it came from, and every later use of it keeps that audience (see [Thread](THREAD.md)).
