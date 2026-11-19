# Plan: personal expenses

Status: draft. Prerequisite for `bank-import.md`.

## Goal
Users can record expenses that are only theirs, next to the shared flat
expenses. The app becomes a personal expense tracker that also handles
the flat. Shared balances and settlements work exactly as today.
Personal expenses are visible only to their owner.

## Approach
- No new expense type and no schema change. A personal expense is an
  ordinary expense where the same user pays and consumes:
  `[(me, -12.50), (me, +12.50)]`. Shares sum to zero (ADR 0003), the
  user's balance does not move.
- "Personal" is derived: an expense is personal when all its shares
  belong to one user. Adding a flatmate to it makes it shared; removing
  everyone else makes it personal. No flag to keep in sync.
- Mixed purchases already work: pay 50, own part 35, flatmate 15 is
  `[(me, -50), (me, +35), (flatmate, +15)]`. It is shared (two users),
  and the user's consumed share (35) counts as their spending.
- A user's spending = sum of their positive shares over all
  non-settlement expenses, shared and personal. This is what the Stats
  tab already computes (`consumedBy`), so personal expenses show up
  there without extra logic.

## Privacy
- A personal expense is visible to its owner only. Not to flatmates
  (they never had a share anyway) and **not to admin**.
- This is an exception to ADR 0001 ("admin sees all data"). Record it
  in a new ADR: personal financial data (personal expenses, later bank
  data) is private to its owner. Admin still sees every shared expense.
- Admin cannot create personal expenses: admins never take part in
  expenses (ADR 0001 stays in force for that).
- A deactivated user's personal expenses stay hidden. Deleting a user is
  already refused while they have shares; that rule stays.

## Backend
- One helper `is_personal(expense)`: non-empty shares, one distinct
  `user_id`. Settlements are never personal (they always have two users).
- `_can_view`: admin sees an expense unless it is personal and not
  theirs. Owner sees it as today (has a share).
- `GET /api/expenses/`: new optional `scope=all|shared|personal`
  (default `all`). Admin: personal expenses of others are always left
  out, also with `user_id=`.
- `GET /api/expenses/categories`: same filter, so admin does not see
  categories used only in someone's personal expenses.
- `PATCH/DELETE`: unchanged rule (admin or payer), but admin gets 404 on
  someone else's personal expense, same as for a missing one, so its
  existence does not leak.
- Response field `personal: bool` on expenses, so the frontend does not
  repeat the rule.
- Balances and settlements: no change. Personal expenses add zero.
- No new table, no migration (ADR 0002 not touched).

## Frontend
- Quick add (`expense-new.js`) and `share-form.js`: a "Just me" option
  next to the split choices. It sets the user as only payer and
  consumer. The default for new expenses stays "shared".
- `/expenses`: filter All / Shared / Personal. Personal rows get a small
  "Personal" tag. CSV export respects the filter.
- Dashboard (`app.js`): "Recent" shows shared expenses only. It is the
  flat view.
- User page Stats tab (`user.js`): toggle Total / Shared / Personal.
  Total is the default for your own page. When admin opens a user's
  page, stats only cover shared expenses.
- Category list: personal and shared expenses share one category list
  per user, as today.

## Testing
- Personal expense: create, balance unchanged, appears in owner's list
  with `personal: true`.
- Becomes shared when a flatmate is added by PATCH, and back.
- Admin: not in list (with and without `user_id`), 404 on GET, PATCH
  and DELETE, its category not in `/categories`.
- Flatmate: 403/404 as today.
- Admin cannot create one (admin share refused as today).
- `scope` filter: all / shared / personal on a mixed set.
- Settlement with two users never counts as personal.
- Frontend stats: mixed purchase counts only the own share.

## Later, optional
- Monthly budget per category for personal spending.
- Recurring personal expenses (rent share, subscriptions).
- Bank import (`bank-import.md`) creates personal expenses in one click.

## Decisions to record
- ADR: scope widens from flat splitting to personal expense tracking;
  personal = all shares belong to one user, derived, no new type.
- ADR: personal financial data is private to its owner, admin included
  (exception to ADR 0001 "admin sees all"). Also covers bank data.
