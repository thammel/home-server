# 0006. Personal financial data is private to its owner, admin included

- **Status:** accepted
- **Date:** 2026-11-18
- **Relates to:** ADR 0001 (amends "admin sees all data"), ADR 0005, `_can_view` in `app/routers/api/expenses.py`

## Context

ADR 0001 lets admins see all data unfiltered. That was harmless while every expense was a shared flat expense. With personal expenses (ADR 0005) and a planned bank import, the app holds a user's private spending and bank transactions. Nobody else, including the person running the app, needs to read another user's private spending.

## Decision

Personal expenses, and later bank connections and transactions, are visible only to their owner. Admins do not see them in lists, stats or categories, and get 404 on them, so their existence does not leak. Admins still see every shared expense.

## Consequences

**Good:** users can track private spending in the app without exposing it. One rule covers personal expenses and bank data.

**Bad:** "admin gets everything" no longer holds; every query that serves admin needs the private filter, and forgetting it leaks data. Admin cannot help fix or clean up a user's personal records. Data is still readable by anyone with access to the server or the DB backups: this is privacy inside the app, not encryption.

**Neutral:** admins cannot create personal expenses anyway, since they never take part in expenses (ADR 0001).

## Alternatives considered

| Option | Why not |
|---|---|
| Admin sees everything (ADR 0001 as is) | Exposes private spending and bank data to another person |
| Per-user setting to share personal data with admin | No use case yet; adds a second access path to test |
| Encrypt personal data per user | Large effort; server-side search and stats would need the key |

## Revisit when

An admin needs to repair a user's personal data, or users ask to share personal spending with someone.
