# Alternative Architecture: Hybrid Streaming & Batch

## Context
While ADR-2 establishes daily batch processing as the standard for Atlas, business requirements may evolve to require low-latency or real-time insights for specific event-driven metrics (e.g., fraud detection, real-time alerting, or live dashboard updates).

## Proposed Alternative
Implement a **Lambda or Kappa Architecture** overlay for high-priority event streams while keeping daily batch processing for bulk historical data and heavy aggregations.

- **Fast Path (Streaming):** Introduce a lightweight message broker (such as Kafka or Redpanda) and a stream processor (like Flink or Spark Streaming) to ingest high-priority real-time events directly into a low-latency serving layer.
- **Batch Path:** Maintain the existing daily batch pipeline in object storage and warehouse-native transforms for comprehensive historical reporting and heavy analytics.

## Trade-offs & Cost
- **Pros:** Provides sub-second to minute-level freshness for critical use cases without disrupting the robust batch pipeline.
- **Cons:** Significantly increases architectural complexity, introduces maintenance overhead for a message broker, and requires dual-path reconciliation logic to ensure stream and batch data align.
