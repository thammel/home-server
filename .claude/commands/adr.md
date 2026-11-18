---
description: Record an architecture decision, or update an existing one
argument-hint: <topic, e.g. "receipt scanning: vision API or local OCR">
---

Record an architecture decision about: **$ARGUMENTS**

Follow the `decision-record` skill. In short:

1. **Check first.** `ls docs/decisions/` and grep for the topic. If an ADR already covers it, update or supersede that one instead of adding a competing record.
2. **Confirm it is load-bearing.** Reversing it touches more than one module, or it rests on an assumption that could prove false, or a reasonable developer would ask "why is it like this?". If none hold, make the choice and skip the ADR.
3. **Check it is not setup-specific.** Decisions about the user's own server go into `CLAUDE.local.md`, not `docs/decisions/` (public repo).
4. **Write it.** Copy `.claude/skills/decision-record/references/template.md` to `docs/decisions/NNNN-kebab-title.md` with the next free number. Under a page.
5. **Be honest in Consequences.** List what it makes harder, not only what it enables.
6. **Status.** If it rests on an unverified assumption, use `provisional - pending verification` and fill in **Revisit when** with the observation that would settle it.

If the decision was made in this conversation, capture the actual reasoning, including constraints the user stated.
