# HomeServer - Flat Expenses

Small FastAPI app to track shared expenses and compute balances between users.

## Features
- Session-based authentication (cookie)
- Role-based access: admin and regular users
- Users, expenses, and balances API
- Supports multiple payers and multiple consumers per expense
- SQLite storage via SQLAlchemy
- Simple static frontend pages
- Admin screen for user management

## Tech
- Python 3.13
- FastAPI + Uvicorn
- SQLAlchemy + SQLite
- Pydantic v2

## Setup
Create a virtual environment and install dependencies:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

## Run
Start the server:

```powershell
uvicorn app.main:app --reload
```

Then open:
- `http://127.0.0.1:8000/` — login + balances
- `http://127.0.0.1:8000/admin` — user management (admin only)
- `http://127.0.0.1:8000/docs` — OpenAPI docs

## First Start
On first startup (no `expenses.db`), an admin user is created automatically:

| Field    | Value      |
|----------|------------|
| Username | `admin`    |
| Password | `changeme` |

Change this password via the admin screen after first login.

## API Overview

All endpoints except `POST /api/auth/login` require an active session cookie.

### Auth
- `POST /api/auth/login` — log in, sets session cookie
- `POST /api/auth/logout` — log out, clears session cookie

### Users
- `POST /api/users/` — create user (**admin only**)
- `GET /api/users/` — list users
- `GET /api/users/me` — current user
- `GET /api/users/{user_id}` — get user (admin or self)
- `PATCH /api/users/{user_id}` — update name/password (admin or self), update `is_admin` (**admin only**)
- `DELETE /api/users/{user_id}` — delete user (**admin only**, cannot delete self or last admin)

### Expenses
- `POST /api/expenses/` — create expense
- `GET /api/expenses/` — list expenses (admin sees all, others see own)
- `GET /api/expenses/{expense_id}` — get expense
- `PATCH /api/expenses/{expense_id}` — update expense
- `DELETE /api/expenses/{expense_id}` — delete expense

### Balances
- `GET /api/balances/` — net balance per user

## Expense Model
An expense contains a list of shares. Shares use signed values:
- Positive share = consumer (owes)
- Negative share = payer (paid)

Shares must:
- Sum to 0
- Positive total equals total cost
- Negative total equals `-cost`

### Example Expense Payload

```json
{
  "date": "2026-01-03",
  "description": "Pizza",
  "category": "Food",
  "cost": 75.0,
  "currency": "EUR",
  "comment": null,
  "shares": [
    {"user_id": 1, "share": 10.0},
    {"user_id": 2, "share": 15.0},
    {"user_id": 3, "share": 15.0},
    {"user_id": 4, "share": 15.0},
    {"user_id": 5, "share": 20.0},
    {"user_id": 3, "share": -40.0},
    {"user_id": 5, "share": -35.0}
  ]
}
```

## Tests
Install dependencies:
```powershell
pip install -e .[dev]
```

Run:
```powershell
pytest -q
```

## Notes
- Balances are net totals per user, not explicit "who pays who" settlements.
- Sessions roll forward on each authenticated request (30-day TTL).
