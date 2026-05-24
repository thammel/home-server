# CLAUDE.md

Always use caveman mode.

File guide Claude Code (claude.ai/code) when working code this repo.

## What this is
FastAPI app track shared flat expenses. Users log in, record expenses with signed shares, view balances.

## Stack
- Python 3.13, FastAPI, SQLAlchemy (SQLite), Pydantic v2
- Plain HTML/CSS/JS frontend (ES modules, no framework)
- Session-based auth via `httponly` cookie

## Commands

```bash
# Run server
uvicorn app.main:app --reload

# Run all tests
pytest -q

# Run a single test
pytest -q tests/test_api.py::test_create_expense_valid_shares

# Install with dev deps
pip install -e .[dev]
```

OpenAPI docs at `http://127.0.0.1:8000/docs` when running.

## Key files
- `app/main.py` — app entry, DB init, admin bootstrap, route registration, static file mounting
- `app/auth.py` — bcrypt_sha256 hashing, rolling session creation/validation, `get_current_user` dep
- `app/models.py` — `User`, `Expense`, `ExpenseShare`, `UserSession`
- `app/schemas.py` — Pydantic schemas for all request/response shapes
- `app/routers/api/` — `auth`, `users`, `expenses`, `balances` routers
- `app/static/js/api.js` — single source all API calls; add new endpoints here
- `tests/test_api.py` — all tests; uses in-memory SQLite, dependency override pattern

## Auth & sessions
- All endpoints except `POST /api/auth/login` require valid session
- Sessions roll forward every authenticated request (30-day TTL, extended each call)
- `get_current_user` dep in `app/auth.py`; override in tests to skip cookie logic

## Access control rules

**Users:**
- `POST /api/users/` — admin only
- `DELETE /api/users/{id}` — admin only, no self-delete, no last-admin delete
- `PATCH /api/users/{id}` — name/password: admin or self; `is_admin` field: admin only, cannot remove last admin
- `GET /api/users/{id}` — admin or self only

**Expenses:**
- `GET /api/expenses/` — admin sees all; non-admin sees only expenses where they have share
- `GET /api/expenses/categories` — distinct category strings (sorted); same access filter as list
- `GET /api/expenses/{id}` — admin or any user with share in that expense
- `PATCH/DELETE /api/expenses/{id}` — admin or any payer (negative share) in that expense

## Expense share model
Signed floats. Negative = payer, positive = consumer. Must sum to 0; positive sum = cost, negative sum = -cost.

Expense can have multiple payers, multiple consumers. Single user can appear multiple times in shares (e.g., pays some, consumes some).

Share validation in `expenses.py::validate_shares`: nets-to-zero check + positive/negative match cost.

## Balance calculation
`GET /api/balances/` compute net balance per user across all expenses. Not pairwise settlement (different from Splitwise). Each user gets single net number: positive = owed money, negative = owes money.

DB stored `expenses.db` at project root. First startup seeds `admin` / `changeme` via `_seed_admin()` in `main.py`.

## Frontend routing
FastAPI serve HTML pages directly for SPA-like navigation:
- `/` → `index.html` (login + balances)
- `/admin` → `admin.html` (user management)
- `/expenses` → `expenses.html` (create expense; category input has autocomplete datalist)
- `/expenses/{id}` → `expense.html` (view/edit; category input has autocomplete datalist)
- `/users/{id}` → `user.html` (Overview tab: settlements + expense list; Stats tab: monthly stacked bar chart by category)

All JS use ES modules. `api.js` exports `api` object and `redirectToLogin()`.

## User stats tab
`user.html` has two tabs: Overview (settlements + expenses table) and Stats (Chart.js stacked bar chart). Chart groups user's expenses by YYYY-MM month, stacked by category. Rendered lazily on first tab open. No new API needed — uses already-fetched expenses.

## Category autocomplete
`Expense.category` stays free-form string. `GET /api/expenses/categories` returns distinct used categories. Create and edit forms wire a `<datalist>` to the category input so browsers suggest existing values.

## Testing pattern
Two fixtures: `client` (admin session), `non_admin_client` (regular user session). Both use in-memory SQLite (`sqlite://`) with `StaticPool`, override `get_db` + `get_current_user`. Use `create_user(client, name)` helper for setup within tests.