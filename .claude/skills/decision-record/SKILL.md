---
name: decision-record
description: Use before making or changing any non-trivial technical decision in this repo - adding a dependency, changing the schema or migration approach, the share/balance model, auth or session handling, the frontend stack or theme, how a new feature talks to an external service - and whenever new work might contradict how the project already does something. Checks docs/decisions/ first, surfaces conflicts instead of silently diverging, and records load-bearing choices as ADRs. Triggers on "should we use", "let's switch to", "why is it done this way", a change of approach, or a provisional assumption getting verified.
---

# Check decisions before making them

The failure this prevents: a choice was made on purpose months ago, nobody remembers why, and today it gets quietly reversed. The project then has two half-applied designs.

## Before deciding: read what exists

```bash
ls docs/decisions/
grep -ril "<topic>" docs/decisions/
```

Then one of three cases applies.

### 1. An ADR covers it and you agree

Follow it. Don't re-derive or re-explain it in chat. Cite it: "per ADR 0002, new columns go into `_COLUMN_MIGRATIONS`."

### 2. An ADR covers it and the new work contradicts it

**Stop and tell the user.** Don't silently diverge, and don't silently comply either: the ADR may be wrong now. Say:

> ADR 0002 decided X because Y. What you're asking implies not-X. Has Y changed, or is this an exception?

Then act on the answer: supersede the ADR (write the new one, mark the old one `superseded by NNNN`), or record the exception in the code with a comment pointing at the ADR.

Never leave the code and the record disagreeing.

### 3. Nothing covers it

If the choice is **load-bearing**, write an ADR. If not, just make it.

Load-bearing means at least one of:

- Reversing it later would touch more than one module (backend and frontend, or several routers).
- It rests on an assumption that could turn out false (how SQLite behaves, what an external API returns, how big the data gets).
- A reasonable developer would ask "why is it like this?" and the code doesn't answer it.

Naming a variable is not load-bearing. Choosing additive migrations over Alembic is.

## Public repo: no setup details

`docs/decisions/` is committed and the repo is public. ADRs describe the app, not the user's own server. Decisions about the user's own deployment (host, OS, service manager, proxy, paths) go into `CLAUDE.local.md`, never into an ADR.

## Writing one

Copy `references/template.md` to `docs/decisions/NNNN-kebab-title.md`, next free number. Keep it under a page: an ADR nobody reads has failed.

**Consequences** is the valuable part. Include what the decision makes *harder*, not only what it enables. An ADR that lists only upsides was not a decision.

If the decision was made in conversation, record the actual reasoning and the constraints the user stated, not a tidied-up rationalisation.

## Provisional decisions

Some decisions rest on an assumption not yet checked against reality, typically how an external service or library behaves, or what real data looks like. Such an ADR:

- gets `Status: provisional - pending verification`
- names in **Revisit when** the exact observation that would settle it

When the answer arrives, revisit the ADR **before** building further on it. Session start flags provisional ADRs so this isn't forgotten.

Building on a guess is fine. Forgetting it was a guess is not.

## `/reassess`

Walks every ADR and compares it with what the code does now. Run it when picking the project back up after a break.
