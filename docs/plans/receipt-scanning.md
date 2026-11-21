# Plan: receipt scanning

Status: draft. The model choice is still being tested (see Phase 0).

## Goal
A user uploads a photo of a receipt. The app reads shop, date, total and
line items, and pre-fills a new expense. The user always reviews and
confirms before an expense is created. Nothing is booked automatically.

## Approach
- A vision model behind any OpenAI-compatible chat completions endpoint
  does the reading. The app server only stores the upload and queues it.
- One app-wide scanner, configured in `.env`: base URL, API key, model.
  Examples: Ollama on a local GPU machine (`<host>:11434/v1`, no key) or
  a hosted inference service. No secrets in the database.
- The endpoint may be unreachable (GPU machine off, service down).
  Uploads wait in a queue in the database and are processed when the
  model is reachable.
- Feature is off by default. Without config the app behaves as today.

First tests: `gemma4:e4b` (about 7 GB VRAM) read a crumpled thermal
receipt photo and a digital e-receipt with all items and totals correct
in 6-30 s. Only errors: single letters in item names.

## Phase 0: model evaluation (ongoing)
- Collect 10-20 receipts: different shops, discounts, deposit, faded
  print, bad light, long receipts.
- For each: total correct, date correct, items sum equals total.
- Compare models on the same set: local `gemma4:e4b`, hosted
  `qwen3.8-27b` (reasoning `low` vs higher) and
  `mistral-small-4-119b-2603` (reasoning `none`). Record accuracy and
  time per scan.
- Check per endpoint: `temperature: 0` accepted, `response_format` with
  a JSON schema accepted (else force a tool call with the schema).
- Exit: total correct on at least ~90 % of photos. Item names may be
  imperfect, the user edits them anyway.
- Real receipts never go into the repo (they contain partial card
  numbers, loyalty numbers and locations).

## Phase 1: upload and queue
Backend
- New table `receipt_scans` (new table, so `create_all` creates it; no
  column migration, see ADR 0002):
  `id, uploaded_by, created_at, status, image_name, result_json, error,
  attempts, model, expense_id (nullable)`.
  Status: `queued -> processing -> done | failed`, then `accepted`
  after review. Discarding deletes the scan.
- `POST /api/receipts/` (multipart): accepts JPEG and PNG. Limit
  about 15 MB. No HEIC: iOS converts to JPEG when a browser uploads a
  photo.
- On upload, normalise the image: rotate upright from EXIF,
  scale the long side to 2000 px, save as JPEG **without EXIF** (drops
  GPS position). Store under `DATA_DIR/receipts/<uuid>.jpg`.
- `GET /api/receipts/` own scans, `GET /api/receipts/{id}`,
  `GET /api/receipts/{id}/image`, `DELETE /api/receipts/{id}`.
- Access: uploader only (ADR 0006, ADR 0009); other users get 404.
  Admins have no scans (ADR 0001): 403 like bank import, and the list
  returns `enabled: false`.

New dependencies (range in `pyproject.toml`, pin in `requirements.txt`)
- `python-multipart` (FastAPI file uploads)
- `pillow` (ships aarch64 wheels)

## Phase 2: background worker
- One asyncio task started in `lifespan`, next to the backup loop.
- Loop:
  1. Any `queued` scans? If not, sleep 10 s (one cheap DB query).
  2. Check the endpoint (`GET /v1/models`, 3 s timeout). If down, back
     off (1 min, growing to 15 min) and retry.
  3. Take the oldest scan, mark `processing`, call
     `POST /v1/chat/completions` with the image as a base64 data URL,
     a JSON schema in `response_format`, `temperature: 0`, timeout
     300 s. Run the HTTP call in a thread (`asyncio.to_thread`), stdlib
     `urllib` is enough.
  4. Validate the answer with a Pydantic model. Store it, mark `done`.
     Flag a warning when the items do not add up to the total.
  5. Bad answer (HTTP 4xx, invalid JSON, missing image): `attempts += 1`,
     back to `queued`; after 3 attempts mark `failed` with the error
     text. Endpoint down, HTTP 429 or 5xx: back to `queued` without
     counting an attempt, and back off as in step 2.
- On startup, reset scans stuck in `processing` to `queued`.
- With Ollama: the OpenAI-compatible API has no `keep_alive` field. Set
  `OLLAMA_KEEP_ALIVE` on the GPU machine so it frees GPU memory soon
  after the queue is empty.
- Config in `app/config.py`: `RECEIPT_SCANNER_URL` and
  `RECEIPT_SCANNER_MODEL` (both needed, else feature off),
  `RECEIPT_SCANNER_KEY` (optional),
  `RECEIPT_SCANNER_EXTRA` (optional JSON merged into the request, e.g.
  `{"reasoning_effort": "low"}`).

Network and security
- The API key lives only in `.env` (chmod 600). Never stored in the DB,
  never logged, never sent to the frontend.
- Ollama has no authentication. Bind it to a private network interface
  only (VPN/LAN), never expose it to the internet.
- The app only ever sends receipt images to the configured URL. With a
  hosted service, check where it processes data and its terms of use
  before enabling it; flatmates should know receipts leave the house.

## Phase 3: review UI
- New page `/receipts` (`receipts.js`): "Scan receipt" upload button
  (`accept="image/jpeg,image/png"`, no `capture`, so phones offer camera
  and photo library), then the user's scans by status: ready to review,
  being read, could not be read (try again, enter by hand, delete),
  saved. Polls every 15 s while scans are being read. Says when the
  scanner is offline and when it was last reachable.
- Review view (`/receipts?scan=<id>`): receipt image beside the expense
  form (reuses `share-form.js`), pre-filled with description = shop,
  date, cost = total, uploader pays, split equally. Items listed under
  the image; warnings and a different receipt currency shown as notes.
- "Save expense" creates the expense through the existing API, then
  `POST /api/receipts/{id}/accept` links it (`accepted`). "Discard"
  deletes the scan and its image. Deleting the expense puts the scan
  back to `done` for review, like bank lines.
- Entry points instead of a nav link (the mobile tab bar has five fixed
  slots): a card on `/expenses/new` with the number ready to review,
  and a notice on the dashboard when scans are ready.

## Phase 4: later, optional
- Digital e-receipts (PDF with text layer): extract the text
  (`pypdf`) and send text instead of an image. Exact and faster. Only the
  first page is the receipt; bonus/coupon pages must be skipped.
- Split by item: assign single items to people, so a shared shop with
  private items is split correctly. Needs an `expense_items` table.
- Category suggestion from shop name and past expenses.
- Second endpoint as fallback when the first is offline for longer than
  N hours.
- Delete receipt images N days after acceptance.

## Testing
- Unit tests mock the scanner: no Ollama in CI.
- Upload tests use a small generated image, never a real receipt.
- Worker tests: model down (stays queued), bad JSON (attempts grow,
  then failed), success (done, result stored), stuck `processing` reset.
- Access tests: other user cannot read a scan or its image (404);
  admin cannot upload or read (403).

## Backups
- `backup_database` copies only the DB. Receipt images live in
  `DATA_DIR/receipts/`; decide whether to back them up or treat them as
  disposable once accepted.

## Decisions
- ADR 0009: receipt scanning through a queued vision model behind one
  app-wide OpenAI-compatible endpoint, configured in `.env`; scans are
  owner-only (provisional until Phase 0 is done).
