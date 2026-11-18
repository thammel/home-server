# 0002. Schema changes are additive migrations run on startup, without Alembic

- **Status:** accepted
- **Date:** 2026-11-15 (recorded after the fact; in force since PR #8)
- **Relates to:** `migrate()` and `_COLUMN_MIGRATIONS` in `app/db_init.py`

## Context

The app runs on one small SQLite database per flat, and existing installs must keep their data across updates. `Base.metadata.create_all` creates missing tables but never alters existing ones, so new columns broke older databases. The schema changes so far were only new columns with safe defaults.

## Decision

On startup, `migrate()` runs `create_all()` and then adds every missing column listed in `_COLUMN_MIGRATIONS` with `ALTER TABLE ... ADD COLUMN`, then sets `PRAGMA user_version` to `SCHEMA_VERSION`. A new column needs an entry there (with a `DEFAULT` if `NOT NULL`), a bumped `SCHEMA_VERSION` and a migration test.

## Consequences

**Good:** no extra dependency or migration files. Updating means pulling and restarting. Migrations are idempotent, and older code still runs against a migrated database.

**Bad:** renaming, dropping or retyping a column, or moving data, is not supported. Restarting after an update migrates the production database without asking, so it must be backed up before the deploy. There is no downgrade path other than restoring the backup.

**Neutral:** `user_version` is recorded but not yet used to branch logic.

## Alternatives considered

| Option | Why not |
|---|---|
| Alembic | More machinery than a handful of added columns needs |
| Manual SQL per release | Easy to forget on one install; not tested |

## Revisit when

A change needs to rename, drop or retype a column, or transform existing rows.
