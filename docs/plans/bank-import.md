# Plan: bank import (FinTS)

Status: draft. Manual sync only for now. Depends on
`personal-expenses.md`.

## Goal
A user connects their own bank account in their account settings. When
they want, they start a sync, type in their PIN, and the app fetches the
transactions since the last sync (or since a date they choose). They
then go through the new transactions one by one and record each as a
personal expense, split it with flatmates, or ignore it. Nothing is
booked automatically.
Transactions the user does not act on never become visible to anyone
else.

## Approach
- FinTS 3.0 PIN/TAN through the `fints` library (python-fints). A local
  test script already fetched balances and the latest transactions per
  account, with the PIN typed in and no app approval needed.
- Manual sync only. The PIN is typed in for every sync, used for that
  one request and never stored (not in the DB, not in memory afterwards,
  not in logs). No background sync.
- One app-wide FinTS product ID (`FINTS_PRODUCT_ID` env var). Without it
  the feature is off and the settings section is hidden. The product ID
  is never committed.
- Each user connects at most one bank login (several accounts under it
  are fine). Admins cannot connect a bank: they never take part in
  expenses (ADR 0001).
- Bank data belongs to its user only. Admin does **not** see other
  users' transactions. Covered by the "personal financial data is
  private" ADR from `personal-expenses.md`.

## PIN and approvals
- The online banking PIN is not read-only: with the PIN plus a TAN,
  transfers are possible. Treat it as a high-value secret. Send it only
  in the request body over HTTPS, never echo it back, never log it.
- Banks lock the login after a few wrong PINs. A rejected PIN is
  reported to the user and never retried automatically.
- Syncs further back than about 90 days, and PSD2 re-authentication
  roughly every 90 days, can trigger an approval in the banking app.
  Since the user is present during a manual sync, the app supports it:
  the sync returns "approve in your banking app", the user confirms in
  the UI, and the sync continues (see Phase 1, approval flow).
- Later option, not planned now: background sync with the PIN kept in
  memory until restart, or a PSD2 aggregator (consent up to 180 days,
  but a third party sees all transactions).

## Sync range
- Default: from the latest booking date already imported for that
  account, minus 7 days. The overlap catches transactions that are
  booked late with an earlier booking date. Dedupe removes the repeats.
- First sync, or when the user picks it: from a date the user enters
  (date picker in the sync dialog, default 30 days back). Up to today.
- Only booked transactions are imported. Pending ones change date, text
  or amount before booking and would create duplicates.

## Duplicate detection
Two separate problems.

1. **Same bank transaction fetched twice** (overlapping ranges). Hard
   rule, never imported twice:
   - If the bank sends a reference (`end_to_end_reference`,
     `bank_reference` or `customer_reference` in the MT940 data, ignoring
     placeholders like `NONREF` / `NOTPROVIDED`), the key is
     account + reference.
   - Otherwise the key is a hash of account, booking date, amount,
     counterparty IBAN (or name) and purpose text, plus an index for
     identical lines in the same fetch. Two real 4.50 coffees at the same
     shop on the same day stay two rows, but a re-fetch of the same day
     does not add a third.
   - Stored as `dedupe_key` with a unique index.
2. **Transaction already entered by hand as an expense.** Soft rule,
   only a hint in the review step: an expense where the user is a payer,
   with the same amount and a date within 3 days, is shown as "possibly
   already recorded" with a link. The user decides: ignore or create
   anyway.

## Phase 1: connect and sync
Backend
- New tables (new tables, so `create_all` creates them; no column
  migration, see ADR 0002):
  - `bank_connections`: `id, user_id (unique), bank_code, server_url,
    login_name, fints_state (blob, nullable), tan_mechanism,
    last_sync_at, last_error, created_at`.
    `fints_state` is `client.deconstruct(including_private=False)`:
    bank parameters and system ID, no PIN. It saves the bootstrap round
    trip on every sync.
  - `bank_accounts`: `id, connection_id, iban, name, enabled`.
  - `bank_transactions`: `id, account_id, booking_date, value_date,
    amount, currency, counterparty, counterparty_iban, purpose,
    dedupe_key (unique), status, expense_id (nullable), fetched_at`.
    Status: `new -> booked | ignored`.
- Bank code to server URL: start with a small list of known banks plus a
  manual URL field. No full bank directory.
- Depot accounts (no balance/transactions operation in the UPD) are
  skipped.
- Endpoints, all scoped to the current user:
  - `GET /api/bank/` connection, accounts, last sync
  - `PUT /api/bank/` create/update connection (bank, login name)
  - `DELETE /api/bank/` remove connection and all its transactions
  - `POST /api/bank/sync` body: `pin`, optional `since` date. Returns
    counts (new, already known) or an approval request with a `sync_id`
  - `POST /api/bank/sync/{sync_id}/continue` after the user approved in
    the banking app
  - `GET /api/bank/transactions?status=` review list
  - `PATCH /api/bank/transactions/{id}` set `ignored` / back to `new`
- Approval flow: on `NeedTANResponse` with a decoupled challenge, keep
  the open FinTS client in memory under a random `sync_id` for at most
  5 minutes, then drop it (and the PIN with it). `continue` calls
  `send_tan` and finishes the fetch. Only the user who started it may
  continue it.
- The FinTS calls block and are slow: run them with
  `asyncio.to_thread`, one sync per user at a time (lock per user).
- Log the bank's 9xxx response codes; python-fints hides them during
  dialog init behind a generic "PIN wrong?" message.

New dependency (range in `pyproject.toml`, pin in `requirements.txt`)
- `fints` (python-fints, LGPL-3.0). Check the install on the server
  (pure Python plus `mt-940`, `lxml`).

Config in `app/config.py`: `FINTS_PRODUCT_ID`.

## Phase 2: UI
- Account settings (`settings.js`): "Bank account" section.
  Not connected: bank, login name, Connect. Connected: accounts with
  on/off toggles, last sync, Disconnect (`confirmButton`).
- Sync dialog: PIN (password field, `autocomplete="off"`), "since"
  date, prefilled with the default range. After a sync: "12 new, 3
  already known", then go to review. Approval needed: message plus
  "I approved it" button.
- Review page `/bank` (`bank.js`): steps through `new` transactions,
  oldest first, one at a time, with a counter ("3 of 12").
  Per transaction: date, amount, counterparty, purpose, and the
  "possibly already recorded" hint if any.
  Actions:
  - "Personal": one click plus category; creates a personal expense
    (user pays and consumes the full amount).
  - "Split": the expense form (reuse `share-form.js`) pre-filled with
    date = booking date, cost = amount, description = counterparty,
    payer = the user. Covers mixed purchases (own part + flatmates).
  - "Ignore": transfers between own accounts, salary, refunds.
  - "Back".
  Both expense actions go through the existing API, link `expense_id`,
  set `booked` and move to the next one. Incoming money is shown too
  but defaults to ignore.
- A list view of all transactions (filter by status) to undo an ignore.
- Nav badge with the count of `new` transactions.

## Phase 3: later, optional
- Category and split suggestions from past expenses with the same
  counterparty (e.g. rent, internet always split equally).
- Rules: auto-ignore known private counterparties.
- Match incoming transfers from flatmates to open settlements.
- Background sync (PIN in memory until restart) or a PSD2 aggregator.
- Delete `ignored` transactions after N days.

## Testing
- Unit tests mock the FinTS client: no bank in CI, never real data in
  the repo.
- Dedupe: overlapping fetches, two identical same-day payments,
  reference present vs missing, `NONREF` placeholder.
- Hint: expense with same amount within 3 days flagged; other user's
  expense not flagged.
- Sync: wrong PIN reported and not retried; approval flow continues and
  expires after 5 minutes; second concurrent sync for the same user
  refused.
- PIN never appears in DB, logs, responses or error text.
- Access: other user and admin get 404/403 on someone's connection,
  transactions and `sync_id`; admin cannot connect a bank.
- Feature off without `FINTS_PRODUCT_ID`.

## Backups
- Transactions live in the DB, so daily backups contain them. Backups
  are as sensitive as the DB itself. The PIN is never in a backup.

## Decisions to record
- ADR: bank import via FinTS with an app-wide product ID, manual sync,
  PIN never stored; transactions are a review list, never booked
  automatically.
