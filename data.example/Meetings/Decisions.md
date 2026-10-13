---
tags:
- meeting
- decisions
ai_summary: 'Running decision log from the Atlas meetings, as opposed to the architectural
  records: each entry has a date, the decision, who made it and why. Covers the daily-batch
  choice, trimming the usage source to two tables, the part-time analyst arrangement
  and deferring row-level access control to a later milestone.'
content_hash: fadd75d2f42f362b9e91f266fb022549
linked_files:
- Architecture/Decisions
- Overview.md
last_modified: '2026-10-13 18:40:00'
---
# Decision Log (meetings)

Decisions taken in meetings, with enough context that nobody has to re-litigate them.
Technical decisions with lasting structural consequences live in
[[Architecture/Decisions]] instead.

| # | Week | Decision | Decided by | Why |
|---|---|---|---|---|
| 1 | 1 | Billing is the first data source | team, at kickoff | smallest source that exercises the whole pipeline |
| 2 | 1 | Daily batch, not streaming | team, at kickoff | no known use case needs fresher than daily |
| 3 | 2 | Analyst is a part-time team member, not a reviewer | EM | feedback during the build, not after |
| 4 | 5 | Row-level access control deferred to M3+ | operations lead | no external users before M3, so no urgency |
| 5 | 8 | Usage source trimmed to two tables | team | unblocks M2; the rest is unused today |

## Reversed

| # | Week | Decision | Why it was reversed |
|---|---|---|---|
| R1 | 4 | "Keep the spreadsheets running in parallel indefinitely" | parallel maintenance cost more than the migration; now parallel for one month only |

Scope context is in [[Overview]].
