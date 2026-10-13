# Architecture Decision Records

Structural decisions, in the order we made them. Meeting-level decisions are logged
separately in [[Meetings/Decisions]].

## ADR-1: Star schema, not one wide table

**Context.** The first prototype used a single wide table because it was fast to build
and easy to query. By the third source it had 90 columns and most were null.

**Decision.** Model facts and dimensions explicitly.

**Cost.** Analysts have to join. We accepted this because the saved-query layer in M3
hides most joins anyway, and because nullable-column sprawl was already making the
wide table hard to reason about.

## ADR-2: Daily batch, not streaming

**Context.** No known use case needs data fresher than a day. Streaming would add a
message broker and a second failure mode to operate.

**Decision.** Daily batch only.

**Cost.** If a real-time use case appears, this is a rewrite of the extract and load
stages rather than a configuration change. We judged that unlikely enough to accept.

## ADR-3: Transforms run in the warehouse

**Context.** We could transform data in the pipeline before loading, or load raw and
transform in the warehouse with SQL.

**Decision.** Load normalized-but-untransformed data; do business logic in the
warehouse.

**Cost.** Warehouse compute is more expensive than pipeline compute. In exchange, an
analyst can read and change a transform without touching pipeline code, which matters
more to us than the bill at this size.

## ADR-4: Object storage as the landing zone

**Context.** Extract could write straight into the warehouse.

**Decision.** Always land raw bytes in object storage first.

**Cost.** One extra hop and some storage. It has already paid for itself twice: both
times a source silently changed shape, the raw files were what let us tell.

Pipeline design: [[Data-Pipeline]].
