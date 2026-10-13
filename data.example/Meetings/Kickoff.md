---
tags:
- meeting
ai_summary: 'Notes from the Atlas kickoff meeting: attendees, the problem statement
  operations brought, the agreed quarter goals and the decision to start with the
  billing data source. Records the decision to defer streaming ingestion and lists
  the open questions on data ownership. Links back to [[Overview]].'
content_hash: c081c35c48659ae9119a9a89cf642716
linked_files:
- Architecture/Decisions
- Architecture/Data-Pipeline
- Overview.md
last_modified: '2026-10-13 18:40:00'
---
# Kickoff — Atlas

**Date:** week 1, Monday · **Duration:** 90 minutes
**Attendees:** operations lead, two engineers, one analyst, engineering manager

## Problem statement (from operations)

> "We have four versions of the monthly numbers and no way to tell which one is right."

Operations walked through their current Monday routine: three exports, two
spreadsheets, a lot of copy-paste. The recurring pain is not the effort, it is that
nobody trusts the result.

## What we agreed

- Start with **billing** as the first data source. It is the smallest, it is the one
  finance already trusts, and it exercises the whole pipeline end to end.
- Daily batch refresh. We explicitly decided against streaming for now — see
  [[Architecture/Decisions]].
- The analyst joins as a part-time member rather than a reviewer, so we get feedback
  during the build instead of after it.

## Open questions

- Who owns the support data source? Nobody in the room could say.
- Do we need row-level access control in M3, or can that wait?
- What happens to the existing spreadsheets once Atlas is live — frozen or deleted?

## Next steps

1. Engineer A: spike the billing extraction, report back in three days.
2. Engineer B: write up the pipeline design → became [[Architecture/Data-Pipeline]].
3. EM: find the owner of the support data source.

Scope and milestones are tracked in [[Overview]].
