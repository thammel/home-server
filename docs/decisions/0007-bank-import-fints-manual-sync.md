# 0007. Bank import uses FinTS with a manual sync, and the PIN is never stored

- **Status:** accepted (verified 2026-11-19)
- **Date:** 2026-11-18
- **Relates to:** `docs/plans/bank-import.md`, ADR 0005, ADR 0006

## Context

Users want their bank transactions in the app instead of typing every expense. German banks offer FinTS 3.0 (PIN/TAN) for direct access with a registered product ID. FinTS has no long-lived token: every dialog sends the online banking PIN, and that PIN plus a TAN can authorise transfers. A local test with one bank fetched the latest transactions with only the PIN, no app approval. Longer ranges and periodic PSD2 re-authentication can require an approval in the banking app. On 2026-11-19 the implementation was tested end to end against a real bank account. How often later syncs need an approval is still open (see Revisit when).

## Decision

The user starts each sync by hand and types the PIN; it is used for that request only and never stored, logged or returned. One app-wide FinTS product ID comes from config; without it the feature is off. Imported transactions are a review list: the user records each as a personal expense, splits it, or ignores it. Nothing is booked automatically. Duplicates are prevented by a unique key per transaction.

## Consequences

**Good:** no banking secret on the server, in the DB or in backups. No third party sees the transactions. The user reviews every booking.

**Bad:** no background sync; transactions only arrive when the user syncs. Typing the PIN each time is tedious. Approval prompts need an interactive flow that holds an open FinTS dialog in memory for a few minutes. FinTS support, URLs and quirks differ by bank. Adds the `fints` dependency (LGPL-3.0).

**Neutral:** bank data is private to its owner (ADR 0006).

## Alternatives considered

| Option | Why not |
|---|---|
| PIN in memory until restart, daily background sync | PIN stays on the server for weeks; deferred, not ruled out |
| PIN stored encrypted in the DB | Key lives on the same server; anyone with server access can decrypt |
| PSD2 aggregator (consent up to 180 days) | A third party sees all transactions; account and terms needed |
| CSV upload from online banking | Manual export per bank; possible fallback |

## Revisit when

The first real implementation syncs over several weeks: if approval prompts are rare, consider the in-memory background sync; if the bank needs approval on every sync, reconsider an aggregator or CSV upload.
