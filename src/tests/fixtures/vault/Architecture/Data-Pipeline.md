---
tags:
- architecture
ai_summary: 'Technical design of the Atlas ingestion pipeline: a daily batch in four
  stages (extract to object storage, normalize, load into the warehouse, verify),
  with idempotent re-runs keyed by run date. Covers the legacy-ID mapping step for
  support data, the failure and retry behaviour, and why each stage writes its output
  before the next one reads it. Refers to [[Overview]].'
content_hash: 697b8ba64e4101f3de9f85bea823e983
linked_files:
- Meetings/Weekly-Sync
- Overview.md
last_modified: '2026-10-13 18:40:00'
---
# Data Pipeline

Daily batch, four stages. Each stage writes its output to durable storage before the
next stage reads it, so any stage can be re-run on its own.

```
sources ──> extract ──> normalize ──> load ──> verify
              │            │           │         │
            object       object     warehouse  warehouse
            storage      storage     tables     checks
```

## Stages

**Extract.** One job per source (billing, support, usage). Writes raw, unmodified
responses to object storage under `raw/<source>/<run-date>/`. No parsing here on
purpose — when a source changes shape, we want the original bytes to look at.

**Normalize.** Parses raw files into the unified schema. This is where the legacy ID
mapping happens: support tickets reference billing accounts by an old identifier, so
the mapping is applied once here rather than in every query later.

**Load.** Writes normalized data into the warehouse. Keyed by `(source, run_date)`, so
re-running a date replaces exactly that date's rows and nothing else.

**Verify.** Row counts against the source, null checks on required columns, and a
reconciliation of billing totals against the finance export. A failed verification
marks the run bad but leaves the data in place for inspection.

## Idempotency

Every stage is keyed by run date and safe to re-run. This is the single property that
makes operating the pipeline boring: when something breaks, the fix is always "re-run
that date".

## Failure behaviour

- Extract fails → retried three times with backoff, then the run is marked failed.
  Yesterday's data stays queryable.
- Normalize or load fails → no partial writes; the stage is atomic per source.
- Verify fails → data is loaded but flagged; dashboards show a stale-data warning
  rather than silently wrong numbers.

## Open

- Usage source still lands two tables with the wrong schema (see
  [[Meetings/Weekly-Sync]], week 8).
- No alerting on verification failures yet; currently someone checks the run log.

Scope and milestones: [[Overview]].
