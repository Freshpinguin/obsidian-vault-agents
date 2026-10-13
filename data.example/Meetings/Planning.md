# M3 Planning (draft)

Rough notes for the M3 planning session. Not agreed yet — do not treat anything here
as a decision.

## Candidate scope

- Query layer: a saved-query UI rather than raw SQL access.
- First three dashboards: weekly operations summary, support backlog, usage by account.
- Freshness indicator on every dashboard (this keeps coming up and is cheap).

## Things we have been avoiding

- Row-level access control. Deferred twice already. If M3 has external viewers, it
  stops being optional.
- What happens to the old spreadsheets. Someone has to own turning them off.

## Rough sizing

| Item | Guess |
|---|---|
| Saved-query UI | 3 weeks |
| Three dashboards | 2 weeks |
| Freshness indicator | 2 days |
| Access control | unknown, needs security input |
