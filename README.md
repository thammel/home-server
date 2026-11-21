# HomeServer - Flat Expenses

Small self-hosted app to track shared flat expenses and settle up. FastAPI + SQLite, plain HTML/JS frontend, ships as a Docker image.

## Features
- **Quick add**: amount → what → category → done. Defaults: today, you paid, split equally between everyone
- Multiple payers, custom splits, one person can both pay and consume
- **Settle up**: see who pays whom, record a payment with one click
- All expenses with search, filters (category, month, person) and **CSV export**
- Profile with balance, settlements, expenses and a **stats** tab (your share by month/quarter and category)
- Admin: add flatmates (temporary password, they pick their own at first login), deactivate, reset passwords, app settings (app name, settlement mode, currency)
- Session cookies (httponly, 30-day rolling), login throttling, security headers (CSP)
- Daily automatic SQLite backups, health check, auto-restart in Docker
- Mobile-first UI with bottom tab bar, light/dark mode
- **Personal expenses**: track your own spending next to the shared one; private to you, admins included
- **Bank import** (optional, German banks via FinTS): sync with your PIN, then go through new transactions one by one
- **Receipt scanning** (optional): photograph a receipt, a vision model reads shop, date, total and items in the background, you check and save

Admin is a manager role, not a flatmate: admins never take part in expenses or balances.

## Run with Docker (recommended)

```bash
git clone <repo-url> flat-expenses && cd flat-expenses
cp .env.example .env          # optional: set ADMIN_PASSWORD, PORT, TZ ...
docker compose up -d --build
```

Open `http://<server-ip>:8000` and log in as `admin` / `changeme` (or your `ADMIN_PASSWORD`). Without `ADMIN_PASSWORD` you must pick a new password at first login. Then add flatmates under **Admin**.

### Without the source: published image

Every release pushes an image to `ghcr.io/thammel/home-server` (amd64 and arm64). Only the compose file and a `.env` are needed:

```bash
mkdir flat-expenses && cd flat-expenses
curl -fsSLO https://raw.githubusercontent.com/thammel/home-server/main/docker-compose.release.yml
curl -fsSL https://raw.githubusercontent.com/thammel/home-server/main/.env.example -o .env
docker compose -f docker-compose.release.yml up -d
```

Update: `docker compose -f docker-compose.release.yml pull && docker compose -f docker-compose.release.yml up -d`. To stay on one version, set `APP_VERSION=1.2.0` in `.env`; the default is `latest`. Tags: `X.Y.Z`, `X.Y`, `latest`.

The container:
- restarts automatically after crashes and server reboots (`restart: unless-stopped`)
- reports its state via a health check (`docker ps` shows `healthy`)
- keeps the database and backups in the named volume `data` (survives rebuilds/updates)
- runs as an unprivileged user, logs are rotated (3 × 10 MB)

### Ubuntu server setup

```bash
# Docker Engine + compose plugin (official convenience script)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER   # log out and back in afterwards

git clone <repo-url> ~/flat-expenses && cd ~/flat-expenses
cp .env.example .env && nano .env
docker compose up -d --build
```

Docker's service starts on boot, so the app comes back after a reboot.

### Everyday commands

| What | Command |
|---|---|
| Status / health | `docker compose ps` |
| Logs | `docker compose logs -f` |
| Update to latest code | `git pull && docker compose up -d --build` |
| Stop / start | `docker compose stop` / `docker compose start` |
| Copy backups to the host | `docker compose cp app:/data/backups ./backups` |

### Backups & restore

A copy of the database is written to `/data/backups/expenses-YYYY-MM-DD.db` at startup and every 24 h. The last `BACKUP_KEEP` (default 14) are kept. Copy them off the server now and then (see table above).

Restore a backup:

```bash
docker compose stop
docker run --rm -v flat-expenses_data:/data -v "$PWD/backups":/restore alpine sh -c \
  "cp /restore/expenses-2026-01-31.db /data/expenses.db && rm -f /data/expenses.db-wal /data/expenses.db-shm && chown 1000:1000 /data/expenses.db"
docker compose start
```

The volume is named `<folder>_data` (check with `docker volume ls`).

Scanned receipt photos live in `/data/receipts/` and are not part of these backups.

> `docker compose down -v` **deletes the volume with all data**. Use `docker compose down` (no `-v`) to just remove the container.

### HTTPS (optional)

To use it outside your LAN, put a reverse proxy in front, e.g. [Caddy](https://caddyserver.com/):

```
expenses.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Then set `COOKIE_SECURE=true` in `.env`. Compose publishes the port on `127.0.0.1` only and trusts the proxy's `X-Forwarded-For` header, so the login throttle sees real client IPs.

## Configuration

All settings are environment variables (see `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | `8000` | Host port (compose only) |
| `TZ` | `Europe/Berlin` | Timezone for logs and backup names |
| `ADMIN_USERNAME` | `admin` | Initial admin name (first start only) |
| `ADMIN_PASSWORD` | – | Initial admin password; unset = `changeme` + forced change |
| `COOKIE_SECURE` | `false` | `true` when served over HTTPS |
| `SESSION_TTL_DAYS` | `30` | Login lifetime, extended on use |
| `BACKUP_KEEP` | `14` | Daily backups to keep, `0` disables |
| `LOGIN_MAX_FAILURES` / `LOGIN_WINDOW_SECONDS` | `5` / `900` | Login throttling |
| `DATA_DIR` | project root (`/data` in Docker) | Where `expenses.db` and `backups/` live |
| `DATABASE_URL` | `sqlite:///$DATA_DIR/expenses.db` | Override the database location |
| `FINTS_PRODUCT_ID` | – | Turns on the bank import (see below) |
| `RECEIPT_SCANNER_URL` / `RECEIPT_SCANNER_MODEL` | – | Turn on receipt scanning (see below) |
| `RECEIPT_SCANNER_KEY` | – | API key for the scanner, if it needs one |
| `RECEIPT_SCANNER_EXTRA` | `{}` | JSON merged into every scan request |
| `RECEIPT_MAX_BYTES` | `15728640` | Largest accepted photo |

App name, currency and settlement mode are set in the app under **Admin → Settings**.

## Bank import (FinTS)

FinTS (formerly HBCI) is the standard online banking interface of German banks. The app uses it to fetch your account transactions, so you do not type every card payment by hand.

1. Register a product ID with Die Deutsche Kreditwirtschaft ([form](https://www.hbci-zka.de/register/prod_register.htm), free, takes a few days). Banks refuse unregistered clients.
2. Set `FINTS_PRODUCT_ID` in `.env` and restart. Without it the bank import stays hidden.
3. As a flatmate, open **Account settings → Bank account** and enter your bank code (BLZ), your bank's FinTS URL and your online banking username (not the PIN). Your bank publishes the URL, for example `https://fints.ing.de/fints/` for ING. After the first sync, switch off accounts you do not want (e.g. savings).
4. On the **Bank** page, enter your PIN and sync. Approve in your banking app if the bank asks.
5. Go through the new transactions: record each as a personal or a shared expense, or ignore it.

The PIN is used for one sync only and is never stored or logged. Incoming money goes straight to the ignored list. Transactions and connection details are visible to their owner only, admins included. Admins cannot use the bank import.

## Receipt scanning

Flatmates upload a photo of a receipt or an e-receipt PDF on **Add → Scan receipt**. A language model reads it in the background and pre-fills an expense; nothing is saved until you check it and press Save.

1. Pick a model that reads images and serve it behind an OpenAI-compatible API: [Ollama](https://ollama.com) on a machine with a GPU (`http://<host>:11434/v1`, no key), or a hosted inference service.
2. Set `RECEIPT_SCANNER_URL` and `RECEIPT_SCANNER_MODEL` (plus `RECEIPT_SCANNER_KEY` if needed) in `.env` and restart.
3. Uploads wait in a queue while the scanner is offline and are read once it is back. A scan that gets three unusable answers is marked as failed and can be retried or entered by hand.

When the receipt has line items, you can split it **by lines**: tap who each line is for (everyone, you, one flatmate, or any group). Each line is split equally within its group and the shares are worked out for you. Lines that are only yours can be kept private: they are then saved as a separate personal expense. The lines stay with the expense and are shown on its page; if someone later edits the shares by hand, the page says that they no longer match.

Photos are turned upright, scaled down and stored without EXIF data (no GPS position). From a PDF only its text and a picture of the first page are kept; the text goes to the model instead of an image. A PDF without text (a scan) is read like a photo. They are sent to the configured URL only. With a hosted service, check where it processes data and tell your flatmates: receipts can show partial card numbers and loyalty numbers. Scans are visible to their uploader only, admins included. Accepted photos stay until you delete them.

## Local development

Requires Python 3.13.

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
uvicorn app.main:app --reload
pytest -q
```

Pages: `/` home, `/expenses` list, `/expenses/new` quick add, `/expenses/{id}` detail/edit, `/users/{id}` profile + stats, `/users/{id}/settings` account, `/admin`. API docs at `/docs`.

The schema is migrated automatically at startup (new columns are added to existing databases).

## API overview

All endpoints except `POST /api/auth/login` and `GET /api/health` require a session cookie.

### Auth
- `POST /api/auth/login` — log in, sets session cookie (429 after too many failures)
- `POST /api/auth/logout` — log out, clears session cookie

### Users
- `POST /api/users/` — create flatmate (**admin**), starts with `must_change_password`
- `GET /api/users/` — list users
- `GET /api/users/me` — current user
- `GET /api/users/{id}` — get user (admin or self)
- `PATCH /api/users/{id}` — name/password (admin or self; own password needs `current_password`), `is_admin` / `is_active` (**admin**)
- `DELETE /api/users/{id}` — **admin**; refused for users with expenses (deactivate them instead), self, or the last admin

### Expenses
- `POST /api/expenses/` — create expense (currency defaults to the app setting)
- `GET /api/expenses/?user_id=` — list, newest first (admin sees all, others their own)
- `GET /api/expenses/categories` — distinct categories
- `GET /api/expenses/{id}` — get (admin or participant)
- `PATCH /api/expenses/{id}` — partial update (admin or payer); nothing is saved if validation fails
- `DELETE /api/expenses/{id}` — delete (admin or payer)

### Receipts
- `GET /api/receipts/` — `enabled`, own scans, scanner reachability
- `POST /api/receipts/` — upload a JPEG/PNG photo or a PDF (multipart `file`), queued for scanning
- `GET /api/receipts/{id}`, `GET /api/receipts/{id}/image` — own scan and its photo
- `POST /api/receipts/{id}/split` — save as expense(s) split by lines; the server derives the shares (`private_own` moves your own lines into a personal expense)
- `POST /api/receipts/{id}/accept` — link an expense saved by hand; `POST /api/receipts/{id}/retry` — queue a failed scan again
- `DELETE /api/receipts/{id}` — delete scan and photo

### Balances & settings
- `GET /api/balances/` — net balance per flatmate
- `GET /api/balances/settlements/?mode=simplified|full` — who pays whom (mode defaults to the app setting)
- `GET /api/settings/`, `PATCH /api/settings/` (**admin**) — `app_name`, `settlement_mode`, `currency`
- `GET /api/health` — health check

## Expense model
Shares are signed: negative = paid, positive = consumed. They must sum to 0, positives must equal the cost. Amounts are rounded to cents.

```json
{
  "date": "2026-01-03",
  "description": "Pizza",
  "category": "Food",
  "cost": 75.0,
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

A settlement payment is stored as an expense with category `Settlement` (payer −amount, receiver +amount).
