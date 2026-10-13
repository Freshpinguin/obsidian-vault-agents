---
tags:
- project
ai_summary: 'Project overview for Atlas, the internal analytics platform: goals for
  the current quarter, scope boundaries, the three delivery milestones and the core
  team. Names the success metrics (query latency, adoption) and points to [[Architecture/Data-Pipeline]]
  for the technical design and [[Meetings/Kickoff]] for the original scoping discussion.'
content_hash: 38d6a21e78618b7fee4f6b7e50511f1f
linked_files:
- Meetings/Stakeholders
- Architecture/Data-Pipeline
- Meetings/Kickoff
last_modified: '2026-10-13 18:40:00'
---
# Atlas — Project Overview

Atlas is the internal analytics platform that replaces the three spreadsheet-based
reporting flows the operations team maintains by hand today.

## Why we are doing this

Operations currently spends roughly a day and a half each week rebuilding the same
reports. The numbers disagree between teams because every report pulls from a
slightly different export. Atlas gives everyone one queryable source.

## Goals for this quarter

1. One ingestion pipeline covering the billing, support and usage data sources.
2. A query layer the operations team can use without writing SQL.
3. Daily refresh, with a clear freshness indicator on every dashboard.

## Out of scope

- Real-time streaming. Daily batch is enough for every known use case.
- Replacing the finance team's reconciliation process.
- External/customer-facing dashboards.

## Milestones

| Milestone | Target | Status |
|---|---|---|
| M1 — billing source ingested end to end | week 4 | done |
| M2 — support + usage sources, unified schema | week 8 | in progress |
| M3 — query layer and first three dashboards | week 12 | not started |

## Success metrics

- p95 dashboard query under 2 seconds.
- Operations reports rebuilt by hand: zero by end of quarter.
- At least five people outside the project team running their own queries.

## Team

Four people, roughly 60% allocated. See [[Meetings/Stakeholders]] for who signs off
on what. The technical design lives in [[Architecture/Data-Pipeline]], and the
original scoping conversation is captured in [[Meetings/Kickoff]].
