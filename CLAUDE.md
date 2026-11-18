# CLAUDE.md

Always use caveman mode.

File guide Claude Code (claude.ai/code) when working code this repo.

## GOLDEN RULE
**NEVER push to git `main`. Ever.** Work on feature branch, commit there. Push only feature branch, only when user ask. Merges to main go via PR on GitHub.

## What this is
FastAPI app track shared flat expenses. Users log in, record expenses with signed shares, view balances, settle up. Runs with uvicorn directly or as Docker image (docker compose).

## Stack
- Python 3.13, FastAPI, SQLAlchemy (SQLite, WAL), Pydantic v2
- Plain HTML/CSS/JS frontend (ES modules, no framework, no build step). Pico CSS + Chart.js vendored in `app/static/vendor/` (no CDN)
- Session-based auth via `httponly` cookie

## Commands

```bash
# Run server (dev)
uvicorn app.main:app --reload

# Run all tests
pytest -q

# Run a single test
pytest -q tests/test_api.py::test_create_expense_valid_shares

# Install with dev deps
pip install -e .[dev]

# Docker
docker compose up -d --build
docker compose logs -f
```

OpenAPI docs at `http://127.0.0.1:8000/docs` when running.

Local dev env (Linux) uses uv: `uv venv --python 3.13 && uv pip install -e '.[dev]' ruff`. Hooks call `.venv/bin/pytest` and `.venv/bin/ruff` directly.

## Deployment
- Host-specific details (server, paths, service, proxy) live in `CLAUDE.local.md` (gitignored). Never copy them into tracked files, commits or PR text: the repo is public.
- Releases are tags (ADR 0008). The server runs a release tag, not the tip of `main`. Merging a feature PR does not ship it; merging the release PR does.
- Migrations run on the first restart after checking out a new tag. Back up the DB before.
- Never change files on the server directly. Every change goes through git.
- The production `expenses.db` is real data. Never delete, overwrite or run migrations against it without the user's explicit go-ahead.
- Migrations run automatically on startup (see Schema changes), so the next restart after a schema change migrates the production DB. Back it up first.

## Decisions
- Load-bearing choices are recorded as ADRs in `docs/decisions/` and listed at session start.
- Before changing how the project does something, use the `decision-record` skill: follow an existing ADR, or tell the user when new work contradicts one. Never leave code and ADR disagreeing.
- `/adr <topic>` records a decision, `/reassess` checks all ADRs against the code.
- ADRs are public. Decisions about the user's own server go into `CLAUDE.local.md`.

## Claude Code hooks (`.claude/`)
- SessionStart: prints branch, status, recent commits, recorded decisions.
- PreToolUse(Bash): `guard.py` blocks deleting `*.db`, force-push, `git reset --hard`, destructive ssh commands.
- PostToolUse(Write|Edit): ruff format + fix on the edited `.py` file.
- Stop: runs `pytest -q -x` when `app/` or `tests/` Python files changed; failures block stopping.

## Key files
- `app/config.py` — all env-var config (DATA_DIR, DATABASE_URL, COOKIE_SECURE, ADMIN_PASSWORD, BACKUP_KEEP, login throttle). Paths absolute, not cwd-relative
- `app/main.py` — app entry, lifespan (migrate + seed + daily backup task), security headers middleware, `/api/health`, router + page registration (`_PAGES` dict)
- `app/db_init.py` — `migrate()` (create_all + additive column migrations via `_COLUMN_MIGRATIONS`, PRAGMA user_version), `seed()` admin + default settings, `backup_database()`
- `app/app_settings.py` — key/value app settings (`app_name`, `settlement_mode`, `currency`) with defaults
- `app/auth.py` — bcrypt_sha256 hashing, rolling session, `get_current_user`, `require_admin` deps, cookie helpers, `utcnow()`
- `app/models.py` — `User` (is_admin, is_active, must_change_password), `Expense`, `ExpenseShare`, `UserSession`, `AppSetting`
- `app/schemas.py` — Pydantic schemas; validation (name/password lengths, cost > 0, cents rounding, currency code)
- `app/routers/api/` — `auth` (login throttle), `users`, `expenses`, `balances`, `settings`
- `app/static/js/` — see Frontend below
- `tests/test_api.py` — all tests; `tests/conftest.py` points DATA_DIR at temp dir
- `Dockerfile`, `docker-compose.yml`, `.env.example`, `requirements.txt` (pinned runtime deps for image)

## Schema changes
No Alembic. New column → add to model AND append `(table, column, DDL)` to `_COLUMN_MIGRATIONS` in `db_init.py`, bump `SCHEMA_VERSION`. DDL needs DEFAULT for NOT NULL. Add migration test.

## Auth & sessions
- All endpoints except `POST /api/auth/login` and `GET /api/health` require valid session
- Sessions roll forward (30-day TTL), expiry written at most once per hour
- Inactive user → session rejected, login refused
- Own password change needs `current_password`; clears `must_change_password`, logs out other sessions. Admin reset of other user sets `must_change_password` + kills their sessions
- New users created by admin start with `must_change_password=True`; frontend `boot()` forces them to settings page
- Login throttle: in-memory, per (client IP, name), `LOGIN_MAX_FAILURES` in `LOGIN_WINDOW_SECONDS` → 429
- `get_current_user` dep in `app/auth.py`; override in tests to skip cookie logic

## Admin vs user identity

**Admin is NOT a user.** Admin is manager/observer, never participant.
- Backend rejects admins (and inactive users) as share participants in new expenses (`validate_share_users`). Users already in an expense may stay when it's edited (legacy data / deactivated users)
- Balances/settlements exclude admins and settled inactive users (`_participants` in balances.py). Legacy admin shares still counted so sums stay correct
- Admin gets full unfiltered views. When adding features that show "your data": admin gets all data
- Frontend: admin has no "Me" profile, nav shows Admin instead

## Access control rules

**Users:**
- `POST /api/users/` — admin only
- `DELETE /api/users/{id}` — admin only, no self-delete, no last-active-admin delete, **refused (409) if user has expense shares** → deactivate instead (deleting shares would break zero-sum and erase debts)
- `PATCH /api/users/{id}` — name/password: admin or self; `is_admin`/`is_active`: admin only; cannot remove/deactivate last active admin; cannot deactivate self
- `GET /api/users/{id}` — admin or self only

**Expenses:**
- `GET /api/expenses/?user_id=` — admin sees all (optional user filter); non-admin only own (other user_id → 403). Sorted date desc
- `GET /api/expenses/categories` — distinct category strings (sorted); same access filter as list
- `GET /api/expenses/{id}` — admin or any user with share in that expense
- `PATCH/DELETE /api/expenses/{id}` — admin or any payer (negative share). PATCH validates everything before mutating (no partial writes); all fields optional

**Settings:** GET any user; PATCH admin only. `app_name` (1–40 chars) is injected server-side into every page via `{{APP_NAME}}` placeholder in the HTML (escaped) — never hardcode the app name; nav brand reads `settings.app_name`.

## Expense share model
Signed floats, rounded to cents on input. Negative = payer, positive = consumer. Must sum to 0; positive sum = cost, negative sum = -cost.

Expense can have multiple payers, multiple consumers. Single user can appear multiple times in shares (e.g., pays some, consumes some).

Settle-up payment = expense with category `Settlement`, payer −amount, receiver +amount. Stats/lists treat category `settlement` (case-insensitive) as payment, not spending.

Currency: one app-wide currency (Admin setting). New expenses get it by default. Balances do not convert currencies.

## Balance calculation
`GET /api/balances/` compute net balance per user across all expenses. Positive = owed money, negative = owes money. `GET /api/balances/settlements/` → simplified (fewest transfers) or full (pairwise); mode param optional, defaults to app setting.

DB `expenses.db` in `DATA_DIR` (default project root, `/data` in Docker). First startup seeds admin (`ADMIN_USERNAME`/`ADMIN_PASSWORD`, else `admin`/`changeme` + forced change).

## Frontend
FastAPI serve HTML skeletons; JS builds UI. Pages (`_PAGES` in main.py):
- `/` → `index.html` + `app.js` (login card, or dashboard: balance hero, settle up, recent)
- `/expenses` → `expenses.js` (list, search, filters, CSV export)
- `/expenses/new` → `expense-new.js` (quick add)
- `/expenses/{id}` → `expense.js` (detail, edit, delete)
- `/users/{id}` → `user.js` (Overview + Stats tabs; stats = user's consumed share by month/quarter, stacked by category)
- `/users/{id}/settings` → `settings.js` (name, password; forced first-login password change)
- `/admin` → `admin.js` (users, add flatmate, settings)

Shared modules:
- `api.js` — single source all API calls; add new endpoints here. Errors carry `.status` and readable `.message` (FastAPI `detail`)
- `ui.js` — `el()` DOM builder, `mount()`, money format (Intl, app currency), `parseAmount` (accepts comma), `splitEqually` (cents), `safeNext`, `confirmButton` (two-step), `toast`
- `layout.js` — `boot()` auth guard + settings + nav (top bar desktop, bottom tab bar mobile); `showFatal()`
- `share-form.js` — expense form for add + edit (single/multiple payers, equal/custom split)
- `settlements.js` — settlement list + "Mark paid" (records Settlement expense)
- `expense-list.js` — expense rows, `netFor`, `consumedBy`, `payerNames`

**Rules:** build DOM with `el()`/textContent only — never `innerHTML` with data (CSP is `script-src 'self'`, no inline scripts/handlers). Use `mount()` not `replaceChildren()` when children may be null/false.

## Docker / deploy
- Image: python:3.13-slim, deps from pinned `requirements.txt`, runs as uid 1000, `DATA_DIR=/data` volume, HEALTHCHECK on `/api/health`
- Compose: `restart: unless-stopped`, named volume `data`, log rotation, optional `.env`
- Daily backup to `/data/backups` (`BACKUP_KEEP`)
- When adding runtime dependency: add range to `pyproject.toml` AND pin in `requirements.txt`

## Testing pattern
Two fixtures: `client` (admin session), `non_admin_client` (regular user "TestUser" + second regular user "OtherUser"). Both use in-memory SQLite (`sqlite://`) with `StaticPool`, override `get_db` + `get_current_user`. Helpers: `create_user(client, name)`, `_user_id(client, name)`, `post_expense(client, [(user_id, share), ...])`, `balances_by_name(client)`. Login throttle reset automatically per test. `test_real_app_boots_seeds_admin_and_serves_pages` runs real app (lifespan, pages, headers) on temp DATA_DIR.

## Code comments
- Default to no comment. Well-named functions and variables should explain *what* the code does.
- Only comment to explain *why*: non-obvious decisions, workarounds, edge cases, links to issues/specs, or surprising behavior.
- Never write comments that restate the code, narrate your changes, or address the reader (e.g. "# Added error handling", "# Updated to use new API").
- Don't leave comments about what was removed or changed. That belongs in the commit, not the code.
- Keep docstrings for public APIs short: one line summary, then params/returns only if non-obvious.

## Releases
- release-please (`.github/workflows/release.yml`) keeps a release PR open on `main`. It bumps `version` in `pyproject.toml` and writes `CHANGELOG.md` from Conventional Commits.
- Merging the release PR tags `vX.Y.Z` and publishes a GitHub Release. Never edit `CHANGELOG.md`, the version or `.release-please-manifest.json` by hand.
- Version bump comes from commit types: `fix` patch, `feat` minor, `type!:` or `BREAKING CHANGE:` footer major. PR squash titles must be Conventional Commits too.
- The same workflow pushes the image `ghcr.io/thammel/home-server` (`X.Y.Z`, `X.Y`, `latest`; amd64 + arm64). `docker-compose.release.yml` runs it without a checkout.
- Deploy: fetch tags, check out the release tag, restart. Rollback: check out the previous tag, restart (schema changes are additive, ADR 0002, so older code runs on a newer DB).

## Commit messages
Enforced by the git `commit-msg` hook (install: `ln -s ../../.claude/hooks/commit_msg.py .git/hooks/commit-msg`).
- Follow Conventional Commits: `type(scope): summary` (types: feat, fix, refactor, docs, test, chore, perf).
- Summary line: imperative mood, max ~50 chars, no trailing period ("fix(auth): handle expired sessions").
- Leave a blank line, then a body wrapped at 72 chars explaining *why* the change was made and any notable trade-offs. Skip the body for trivial changes.
- Describe the change's intent, not a file-by-file list of what was edited.
- One logical change per commit; if the work spans unrelated concerns, propose splitting it.
- Compact the message to the minimum. Reference issues when relevant (`Closes #123`).
- No emojis, no "This commit...", no marketing language. No Co-authored-by trailer.

## Pull requests
- Title: same format as a commit subject (`type(scope): summary`, imperative, max ~50 chars, no period).
- Body sections, each kept short:
  - `## Why`: the problem or goal in 1-3 sentences. Link issues (`Closes #123`).
  - `## What`: the notable changes and trade-offs as bullets, grouped by intent, not a file-by-file list.
  - `## Testing`: what was run or checked, as a checklist. Say plainly what was not tested.
  - `## Deploy notes` (only when relevant): steps needed on the server, migrations, config/env changes, risk to `expenses.db`.
- One logical change per PR. Mention conflicts with or dependencies on other open PRs.
- No emojis, no marketing language, no "Generated with" footer, no Co-authored-by lines.
