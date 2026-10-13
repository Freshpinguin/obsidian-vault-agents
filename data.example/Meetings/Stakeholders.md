---
tags:
- meeting
ai_summary: 'Who to involve in Atlas and what each person signs off on: the operations
  lead as decision owner, finance for anything touching billing figures, the data
  platform team for the warehouse schema, and security for access control. Includes
  a short note on how often each group expects an update.'
content_hash: 3ccd3e62be89b7b865d658eb00c2d1dc
linked_files: []
last_modified: '2026-10-13 18:40:00'
---
# Stakeholders

Who needs to be involved, in what, and how often.

## Sign-off owners

| Area | Person | Signs off on |
|---|---|---|
| Scope and priorities | operations lead | what is in a milestone |
| Billing figures | finance analyst | anything that produces a number finance also publishes |
| Warehouse schema | data platform team | table layout, naming, retention |
| Access control | security | who can query what, before M3 ships |

## Update cadence

- **Operations lead:** present at the weekly sync, so no separate update needed.
- **Finance:** short written update at each milestone. They care about correctness, not progress.
- **Data platform:** a design review before any schema change lands.
- **Security:** nothing until M3 planning, then a review of the access model.

## Notes

Finance is the group most likely to block a release, and the one least likely to be in
the room when the decision is made. Default to writing things down for them.
