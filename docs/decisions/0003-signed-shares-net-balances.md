# 0003. Expenses are signed shares that sum to zero; balances are one net number per person

- **Status:** accepted
- **Date:** 2026-11-15 (recorded after the fact)
- **Relates to:** `validate_shares` in `app/routers/api/expenses.py`, `app/routers/api/balances.py`

## Context

Flat expenses come in many shapes: one person pays for everyone, several people pay for one purchase, someone pays and consumes, someone settles a debt. The model has to cover all of them without special cases per type.

## Decision

Every expense is a list of signed shares: negative means paid, positive means consumed. Shares must sum to zero, and the positive sum equals the cost. Amounts are rounded to cents on input. A person's balance is the sum of their shares over all expenses. Settling up is an ordinary expense with category `Settlement`. Who-pays-whom is derived from the balances (fewest transfers, or pairwise).

## Consequences

**Good:** one shape covers multiple payers, uneven splits and settlements. Balances are a plain sum, and the zero-sum check catches broken input.

**Bad:** amounts are stored as floats, so every write must round to cents and comparisons need a small tolerance. Settlements are recognised by category name, so stats and lists have to filter `settlement` case-insensitively. There is no history of who owed whom pairwise, only the net position.

**Neutral:** one app-wide currency; balances never convert between currencies.

## Alternatives considered

| Option | Why not |
|---|---|
| Payer + list of debtors per expense | Can't express several payers or a payer who also consumes |
| Pairwise debt ledger (Splitwise style) | More state to keep consistent; net balances are enough for one flat |
| Integer cents in the database | Would need a data migration (see ADR 0002); rounding on input covers it for now |

## Revisit when

Float rounding shows up as a visible cent difference in balances, or multiple currencies need converting.
