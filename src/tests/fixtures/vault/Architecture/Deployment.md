---
ai_summary: Deployment process notes for pipeline jobs running on a shared internal
  cluster scheduler and a managed warehouse. Current workflow involves merging to
  main, CI builds job images, and image-based scheduling. Identified gaps include
  lack of staging environments, absence of rollback mechanisms, and secrets management
  via scheduler configuration rather than a secret store.
content_hash: 4c17282fa4599eeafd0aff4aa393a4f3
linked_files: []
last_modified: '2026-10-13 19:32:43'
---
# Deployment (notes)

Written down from memory after the last deploy; needs review.

## Where things run

- Pipeline jobs: the scheduler on the shared internal cluster.
- Warehouse: managed, operated by the data platform team.
- Query layer: not deployed yet (M3).

## How a deploy happens today

1. Merge to `main`.
2. CI builds the job image and pushes it.
3. The scheduler picks up the new image on its next run.

There is no staging environment for the pipeline. We test against a copy of one day of
billing data on a laptop, which has worked so far and will stop working soon.

## Known gaps

- No rollback other than reverting the commit and waiting for the next run.
- Secrets are in the scheduler's config, not a secret store.
- Nobody has tested what happens if two runs overlap.
