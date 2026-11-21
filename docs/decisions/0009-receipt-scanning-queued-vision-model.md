# 0009. Receipts are read by a vision model behind one configured endpoint, through a queue

- **Status:** provisional - pending verification
- **Date:** 2026-11-21
- **Relates to:** `docs/plans/receipt-scanning.md`, ADR 0001, ADR 0006

## Context

Typing shop, date and total from a paper receipt is the slowest part of
recording an expense. Vision language models can read receipt photos:
first tests on a crumpled thermal receipt photo and a 24-line e-receipt
got total, date and every line item right with a 27B model. A smaller
MoE model got totals right but attached "2 x" quantity lines to the
wrong item. Two receipts are not enough evidence (see Revisit when).
The model can run locally (Ollama on a GPU machine that is not always
on) or at a hosted inference service. Both speak the OpenAI chat
completions API. Hosted services and their models change over time.

## Decision

Uploaded receipts go into a queue in the database. A background worker
sends each one to one app-wide OpenAI-compatible endpoint (URL, key,
model from `.env`) and asks for a JSON-schema answer. The result
pre-fills an expense form; nothing is booked until the user saves it.
Without an endpoint configured the feature is off. Scans and their
images are private to the uploader (ADR 0006); admin cannot upload
(ADR 0001) or view them.

## Consequences

**Good:** any local or hosted model works by changing three settings.
The queue absorbs an offline endpoint, slow models (up to a minute per
receipt) and retries. The API key never enters the DB or backups. A
person checks every result, so model mistakes cost an edit, not a
wrong balance.

**Bad:** with a hosted endpoint, receipt images (partial card numbers,
loyalty numbers, shop locations) leave the server; whoever configures
it must check where data is processed and tell the other users. Results
arrive minutes later, not while the user waits. One key serves all
users, so usage limits are shared. Receipt images need disk space and
are not in the DB backup. Adds `python-multipart`, `pillow` and
`pypdfium2` (parses untrusted PDFs in C++; capped at 5 pages). Only
JPEG, PNG and PDF are accepted.

**Neutral:** e-receipt PDFs (amended 2026-11-21) skip the image: their
text layer goes to the same endpoint as plain text, which is exact,
cheaper and works with text-only models. The model still does the
parsing, because every chain lays out its receipts differently. A PDF
without text is read as a photo of its first page. The model may
misread item names; the user edits them.
The app warns when line items do not add up to the total.

## Alternatives considered

| Option | Why not |
|---|---|
| Classic OCR (Tesseract) plus parsing rules | Poor on crumpled thermal paper; parsing rules per shop layout |
| Synchronous scan during upload | Fails whenever the endpoint is down; long requests on phones |
| Per-user endpoint and key | Secrets in the DB and backups (compare ADR 0007) |
| Ollama-native API | Locks out hosted services; OpenAI-compatible covers both |
| Parse PDF text with rules per shop | Breaks whenever a chain changes its layout; the model already handles all of them |
| Admin may view all scans | Receipts hold card and loyalty numbers; ADR 0006 keeps such data owner-only |

## Revisit when

Phase 0 has 10-20 varied receipts: if the chosen model gets the total
right on fewer than ~90 %, try other models or prompts before building
further. If no model reaches it, reconsider manual entry with the image
attached.
