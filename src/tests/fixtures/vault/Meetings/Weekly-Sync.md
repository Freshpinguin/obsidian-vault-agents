---
tags:
- meeting
ai_summary: 'Format and running log of the Atlas weekly sync: a 25-minute standing
  meeting with a fixed four-part agenda (progress, blockers, decisions needed, next
  week). Contains the notes from the most recent weeks, including the schema disagreement
  in week 6 and the decision to cut the usage source down to two tables.'
content_hash: 048dff39571f517ad88e3c6db829b016
linked_files:
- Meetings/Decisions
- Architecture/Decisions
last_modified: '2026-10-13 18:40:00'
---
# Weekly Sync

A standing 25-minute meeting, Thursdays. Anything that needs more than ten minutes
of discussion gets its own meeting instead.

## Agenda (fixed)

1. What moved since last week (two minutes per person, no slides)
2. Blockers
3. Decisions needed this week
4. What we expect to finish next week

## Week 8

- M2 is close. Support source is ingested; usage source is landing but the schema is
  still wrong for two tables.
- **Blocker:** we are still waiting on read access to the usage replica. Escalated.
- Decision: cut the usage source down to the two tables anyone actually queries, and
  revisit the rest in M3. Logged in [[Meetings/Decisions]].

## Week 7

- Support source ingested end to end, one day ahead.
- Discovered that support tickets reference billing accounts by a legacy ID. Added a
  mapping step to the pipeline rather than a join at query time.

## Week 6

- Long disagreement about whether to model one wide table or a star schema. Parked it
  and took it to a separate design session; outcome is in
  [[Architecture/Decisions]].
- Retro observation: we keep rediscovering decisions we already made in passing, which
  is why the decision log now exists.
