---
tags:
- meeting
- adr
ai_summary: 'The decision log: seven architecture-style decision records covering
  the roster strategy, the no-caging rule, the capybara subsidy, the bat labelling
  compromise, the abandoned penguin line, the unresolved supplier concentration and
  the deferred question of whether the animal matters at all.'
content_hash: 79daaff0453006bbdcd0ecdad7e44b3b
linked_files:
- Market/Customer-Research.md
- Animals/Sloth.md
- Legal/Regulatory.md
- Animals/Capybara.md
- Operations/Supply-Chain.md
- Animals/Bat.md
- Brand/Tasting-Notes.md
- Animals/Penguin.md
- Animals/Civet.md
- Market/Competitors.md
last_modified: '2026-10-13 22:12:22'
---
# Decisions

Decision records, in the order they were made. Each one states the context, the decision
and what it cost us.

## ADR-1: A roster, not a product

**Context.** Every existing producer in this category sells one animal.

**Decision.** Build a roster of many animals.

**Cost.** Nine supply chains instead of one, nine welfare arrangements, nine processing
profiles. In exchange, a collector segment that returns (see
[[Market/Customer-Research]]) and a competitive position no single-animal producer can
copy quickly.

## ADR-2: Never cage, never force-feed

**Context.** Demand for Kopi Luwak outran wild supply and the industry caged civets. The
coffee got worse and the reputation got much worse.

**Decision.** Every animal is fed on its own schedule and is never confined for
production.

**Cost.** Our yields are unpredictable and our forecasting is poor, most visibly on
[[Animals/Sloth]]. This is the constraint the entire operation is built around, and it is
also the only reason [[Legal/Regulatory]] signs off.

## ADR-3: One boring animal pays for the interesting ones

**Context.** The best products have the worst yields.

**Decision.** [[Animals/Capybara]] is the commercial base. Everything else is a halo line.

**Cost.** 70% revenue concentration in one supplier, which is the red entry in
[[Operations/Supply-Chain]] and has been for three quarters.

## ADR-4: Bat coffee is labelled "selected", not "digested"

**Context.** Fruit bats chew and spit the bean. Nothing is digested. It is also our best
coffee.

**Decision.** Sell it as "bat-selected, wild-fermented". No digestion claim.

**Cost.** Our strongest product cannot use our strongest marketing angle. See
[[Animals/Bat]] and [[Brand/Tasting-Notes]].

## ADR-5: Penguin line abandoned

**Context.** "Naturally cold-processed" is an excellent line on a bag.

**Decision.** Abandoned. Penguins are carnivores and coffee does not grow near them.

**Cost.** None, beyond the meeting. The cold was always doing the work, not the penguin.
See [[Animals/Penguin]].

## ADR-6: Second cherry supplier — not done

**Context.** Both cherry farms are in one growing region.

**Decision.** Agreed, then not executed, for three quarters running.

**Cost.** Still an open amber risk. This record exists mainly so the next person to ask
can see that we already agreed and still did nothing.

## ADR-7: The animal question — deferred

**Context.** Our own blind tasting put a plain washed Ethiopian second out of six, ahead
of four of our lines and ahead of [[Animals/Civet]]. Lab ferment startups now reproduce
the flavour with no animal at all (see [[Market/Competitors]]).

**Decision.** Deferred. Formally, explicitly deferred.

**Cost.** If the flavour was never the point, we are a story company with a very expensive
logistics operation, and we should know that before the market tells us. Nobody wants to be
the one to open this, so it sits here, numbered, waiting.
