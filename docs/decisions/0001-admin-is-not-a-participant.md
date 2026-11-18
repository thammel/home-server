# 0001. Admin manages the app and never takes part in expenses

- **Status:** accepted
- **Date:** 2026-11-15 (recorded after the fact; in force since PR #8)
- **Relates to:** `validate_share_users` in `app/routers/api/expenses.py`, `_participants` in `app/routers/api/balances.py`

## Context

The first admin account is created automatically on startup and exists to manage flatmates and settings. Early versions treated it like any user, so it showed up in share pickers and balance lists, and balances included a person who does not live in the flat.

## Decision

Admin is a manager and observer role. Admins cannot be added as share participants in new expenses, are left out of balances and settlements, and always see all data unfiltered.

## Consequences

**Good:** balances only contain flatmates. Admin views need no "whose data" logic: they get everything.

**Bad:** a flatmate who also administers the app needs two accounts. Legacy expenses that already contain admin shares must stay counted so the sums stay zero, so balance code keeps a special case for them.

**Neutral:** the frontend shows "Admin" instead of a "Me" profile for admins.

## Alternatives considered

| Option | Why not |
|---|---|
| Admin as a flag on a normal participant | Mixes two roles; every "your data" feature needs an admin branch anyway |
| Delete legacy admin shares | Breaks the zero-sum of those expenses and erases real debts |

## Revisit when

A flat wants the person who administers the app to also split expenses without a second account.
