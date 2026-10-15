# A superseded clause is marked on the clause, not on the record

Supersedes [ADR-0000](0000-record-decisions-as-madr.md)'s `Superseded by ADR-NNNN` clause, quoted below.

## Context and Problem Statement

ADR-0000 says:

> A decision is never changed by editing its record. A new record names the one it supersedes, and the old record gets `Superseded by ADR-NNNN.` under its title, which is the only edit an accepted record ever gets.

That rule assumes a record is superseded whole. ADR-0009 superseded exactly one line of ADR-0005 — its agent-to-agent clause — and left the rest of 0005 in force. Following 0000 literally would have marked the whole of 0005 superseded, which is false: 0005 still decides what the map names. Not marking it at all would have left a reader of 0005 with no pointer to the record that changed part of it.

So 0009 wrote `Agent-to-agent line superseded by ADR-0009.` under 0005's title. That edit is correct and is not the string 0000 permits. 0000's rule now has a known exception that lives only in the record that broke it, which is the condition this record exists to remove.

## Decision Outcome

A record may be superseded in whole or in part.

When superseded in whole, the rule is unchanged: `Superseded by ADR-NNNN.` under the title, and nothing else.

When superseded in part, the marker names the part: `<clause> superseded by ADR-NNNN.` under the title. The superseding record states which clause it replaces and that the rest of the superseded record remains in force. The named clause must be identifiable in the superseded record without consulting the superseding one.

In both cases this remains the only edit an accepted record ever gets.

### Consequences

* Good, because a reader of a partly superseded record learns that from the record itself rather than by finding the one that replaced it.
* Good, because the alternative in practice was marking a record wholly superseded when it was not, which makes the archive say something untrue.
* Bad, because the marker is now a shape rather than a fixed string, so it cannot be checked by exact match. Naming the clause is a judgement, and a vague name is worse than none.
* Neutral, because partial supersession was already happening; this records the form it takes.

## Confirmation

On acceptance, ADR-0000 carries, under its title: Clause `Superseded by ADR-NNNN` superseded by ADR-0010. That is itself a partial marker in this record's form, and it deliberately does not begin with `Superseded by ADR-`, so neither a reader scanning titles nor a prefix check reads ADR-0000 as wholly superseded.

Every accepted record carrying a supersession marker names either the whole record or a clause identifiable within it. ADR-0005 satisfies this today: its marker names the agent-to-agent line, which is a single identifiable line in that record.
