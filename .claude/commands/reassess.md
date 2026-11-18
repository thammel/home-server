---
description: Compare every recorded decision with what the code does now, and report the drift
---

Re-examine the project's decisions against its current state. This is **read and report** only: change no code or ADR until the findings are shown and the user has picked what to act on.

## 1. Gather

- Read every file in `docs/decisions/`: number, title, status, **Revisit when** trigger.
- For each, read the code it is about. Read narrowly: the ADR says which module to look at.

## 2. Classify each ADR

| Verdict | Meaning |
|---|---|
| **Holds** | Code matches, assumptions still true. One line, no more. |
| **Violated** | Code contradicts an accepted ADR. Say whether the code or the ADR is wrong. |
| **Now answerable** | A `provisional` ADR whose **Revisit when** trigger has happened. Highest-value category. |
| **Superseded in practice** | The code moved on but the record was never updated. |
| **Obsolete** | The context that motivated it no longer exists. |

## 3. Report

Lead with what needs action. For each: the ADR, what changed, the next step. Call out any `provisional` ADR that is still unverified while code was built on it.

End with a short recommendation on what to do first, then stop and let the user choose.

Don't manufacture drift to look thorough. "All decisions hold" is a fine result, reported in a few lines.
