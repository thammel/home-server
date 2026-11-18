# NNNN. <Short imperative title>

- **Status:** proposed | accepted | provisional - pending verification | superseded by NNNN
- **Date:** YYYY-MM-DD
- **Relates to:** feature, PR #N, ADR NNNN

## Context

What forced a decision? State the constraint, not the solution. If it rests on an assumption rather than a verified fact, say so and say where the assumption came from.

## Decision

What we do, in one or two sentences. Present tense, active: "New columns are added by `_COLUMN_MIGRATIONS` on startup."

## Consequences

**Good:** what this buys.

**Bad:** what it costs, what it makes harder, what we give up. *This section is why the ADR is worth writing.*

**Neutral:** what changes without being better or worse.

## Alternatives considered

| Option | Why not |
|---|---|
| ... | ... |

One line each, enough that nobody repeats the evaluation.

## Revisit when

*(Required for `provisional`, good practice otherwise.)*

The specific, observable trigger that should reopen this: "when a migration needs to rename or drop a column", not "when we have time".
