# 0005. Personal expenses are ordinary expenses whose shares all belong to one user

- **Status:** accepted
- **Date:** 2026-11-18
- **Relates to:** `docs/plans/personal-expenses.md`, ADR 0003, ADR 0006

## Context

The app started as a replacement for a shared-expense splitting service: it only knew expenses split between flatmates. Users also want to track their own spending in the same place, and a planned bank import needs somewhere to put transactions that are not shared. Many real purchases are mixed: part shared, part only for the payer.

## Decision

The app tracks personal spending next to shared flat expenses. A personal expense is an ordinary expense in which one user both pays and consumes (`[(me, -x), (me, +x)]`). "Personal" is derived, never stored: an expense is personal when all its shares belong to one user. A user's spending is the sum of their positive shares over all non-settlement expenses, shared and personal.

## Consequences

**Good:** no new type, table or migration. Shares still sum to zero (ADR 0003), so balances and settlements are untouched. Mixed purchases are one expense. Adding or removing a flatmate turns an expense shared or personal without a flag to keep in sync.

**Bad:** every list, stat and access check must know about the derived "personal" state, and it costs a look at the shares. The dashboard and admin views now need a "shared only" filter. The product is no longer only a flat tool, so features have to fit both uses.

**Neutral:** categories are one list per user for shared and personal expenses.

## Alternatives considered

| Option | Why not |
|---|---|
| `is_personal` flag column | Can disagree with the shares; needs a migration (ADR 0002) |
| Separate `personal_expenses` table | Duplicates expense code; mixed purchases need two records |
| Single share with no payer | Breaks the zero-sum rule (ADR 0003) |

## Revisit when

Personal spending needs data that shared expenses do not have (budgets, accounts, recurring rules) and the shared expense model starts bending around it.
