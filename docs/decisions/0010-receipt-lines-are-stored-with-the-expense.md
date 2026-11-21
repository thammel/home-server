# 0010. Receipt lines are stored with the expense and split among groups of people

- **Status:** accepted
- **Date:** 2026-11-21
- **Relates to:** ADR 0003, ADR 0005, ADR 0006, ADR 0009

## Context

A scanned receipt (ADR 0009) yields line items, but only its total
reached the expense. Real receipts mix shared and individual things: a
grocery run holds shared milk and one person's beer, a restaurant bill
holds each person's dish and a bottle of wine shared by two of three.
Splitting such a receipt by hand means adding up lines on a phone.
Later the lines may be grouped and analysed (who buys what), so they
are worth keeping, not only using once.

## Decision

On review, each receipt line is assigned to a group of people
(everyone, one person or any subset). The server derives the consumer
shares from the lines: each line is split equally within its group,
and per-person sums are rounded to cents by largest remainder so they
add up to the total exactly. The payer is the uploader. Lines are
stored in `expense_items` with their people in `expense_item_users`;
"everyone" is stored as the people at save time.

Lines assigned to a flatmate are visible to everyone who can see the
expense, since that is how they check their amount. Lines that belong
only to the payer stay in the expense by default (a restaurant bill is
no secret). A per-receipt option moves them into a separate personal
expense (ADR 0005), which only the payer sees (ADR 0006).

The lines are a record of the split, not the source of the shares.
Shares can still be edited by hand; when they no longer match the
lines, the expense page says so.

## Consequences

**Good:** one tap per line instead of adding up on a phone. The
balance model (ADR 0003) is untouched: shares are still signed numbers
that sum to zero. Lines with their people allow later analysis, also
for groups. Restaurants stay one expense; groceries can keep the
payer's own items private.

**Bad:** two more tables. With the option on, one receipt becomes two
expenses. Lines and shares can drift apart after a hand edit; the app
shows it but does not repair it. Changing a line later means editing
shares by hand. Rounding gives a cent more to some people.

**Neutral:** expenses without a receipt have no lines and work as
before. Deleting an expense deletes its lines.

## Alternatives considered

| Option | Why not |
|---|---|
| Browser computes shares, server stores lines | Two places doing the rounding; server could store lines that do not match |
| Lines always define the shares (edit through lines) | Quick hand fixes no longer possible; heavier edit page |
| Drop line owners on a hand edit | Loses data for analysis |
| One owner per line (everyone or one person) | Wine shared by two of three needs a hand fix |
| Payer's own lines always split off | A restaurant bill becomes two entries |
| Payer's own lines always visible | Groceries show flatmates what you bought for yourself |

## Revisit when

Lines get edited after saving often enough that hand-editing shares is a
nuisance, or analysis needs categories per line.
