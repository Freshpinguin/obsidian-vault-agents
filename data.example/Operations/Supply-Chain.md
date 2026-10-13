---
tags:
- operations
ai_summary: 'Supply chain structure and risk register: transit times per animal, the
  single-supplier concentration on the capybara line that is the company''s only red
  risk, and the two-week forecasting lag the sloth line forces on planning.'
content_hash: 009f7d5337e57365f6dca222aacd817e
linked_files:
- Operations/Retrieval.md
- Animals/Ostrich.md
- Animals/Capybara.md
- Animals/Elephant.md
- Animals/Sloth.md
- Meetings/Decisions.md
last_modified: '2026-10-13 22:12:22'
---
# Supply Chain

Four stages, two of which are not under our control.

## Stages

1. **Cherry in.** Bought from two farms, both in the same growing region. Concentration
   risk flagged below.
2. **Feeding.** On the animal's schedule. See [[Operations/Retrieval]].
3. **Transit.** Inside the animal. Not instrumentable. We wait.
4. **Processing.** Wash, sort, dry, roast. The only stage with a predictable duration.

## Transit times

| Animal | Transit | Forecastable? |
|---|---|---|
| [[Animals/Ostrich]] | under 24 h | yes |
| [[Animals/Capybara]] | 1 to 2 days | yes |
| [[Animals/Elephant]] | 2 to 3 days | mostly |
| [[Animals/Sloth]] | 9 to 14 days | no |

## Risk register

| Risk | Severity | Note |
|---|---|---|
| Capybara single-supplier concentration | **red** | 70% of revenue, one arrangement |
| Both cherry farms in one region | amber | one bad season hits every line at once |
| Sloth forecasting lag | amber | two weeks ahead of unknowable demand |
| Honey badger suspension | green | suspended, so currently risk-free |

The red risk has been red for three quarters. [[Meetings/Decisions]] ADR-6 was supposed to
address it and did not.
