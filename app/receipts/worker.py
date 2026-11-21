"""Background worker: sends queued receipt scans to the scanner, one at a time (ADR 0009)."""

import asyncio
import contextlib
import datetime
import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from app import config, models
from app.auth import utcnow
from app.receipts.scanner import (
    OpenAICompatibleScanner,
    ScanFailed,
    ScannerMisconfigured,
    ScannerUnavailable,
)
from app.schemas import ReceiptResult

log = logging.getLogger("app.receipts")

MAX_ATTEMPTS = 3
_IDLE_SECONDS = 10
_BACKOFF_START = 60
_BACKOFF_MAX = 15 * 60


@dataclass
class ScannerStatus:
    """In memory only, shown in the UI to explain why scans are waiting."""

    last_reachable_at: datetime.datetime | None = None
    last_checked_at: datetime.datetime | None = None
    reachable: bool | None = None

    def record(self, reachable: bool) -> None:
        now = utcnow()
        self.last_checked_at = now
        self.reachable = reachable
        if reachable:
            self.last_reachable_at = now


status = ScannerStatus()


def check_totals(result: ReceiptResult) -> ReceiptResult:
    warnings = []
    if result.items:
        item_sum = round(sum(i.line_total for i in result.items), 2)
        if abs(item_sum - result.total) >= 0.01:
            warnings.append(
                f"Items add up to {item_sum:.2f}, the receipt total is {result.total:.2f}"
            )
    return result.model_copy(update={"warnings": warnings})


def reset_stuck(session_factory: sessionmaker) -> int:
    """A scan left in `processing` was cut off by a restart; queue it again."""
    with session_factory() as db:
        count = (
            db.query(models.ReceiptScan)
            .filter(models.ReceiptScan.status == "processing")
            .update({"status": "queued"})
        )
        db.commit()
    if count:
        log.info("Requeued %d receipt scan(s) interrupted by a restart", count)
    return count


def _next_queued(db: Session) -> models.ReceiptScan | None:
    return (
        db.query(models.ReceiptScan)
        .filter(models.ReceiptScan.status == "queued")
        .order_by(models.ReceiptScan.created_at, models.ReceiptScan.id)
        .first()
    )


def has_queued(session_factory: sessionmaker) -> bool:
    with session_factory() as db:
        return _next_queued(db) is not None


def process_next(session_factory: sessionmaker, scanner) -> bool:
    """Scan the oldest queued receipt. Returns False when the scanner is unavailable."""
    with session_factory() as db:
        scan = _next_queued(db)
        if scan is None:
            return True
        scan.status = "processing"
        db.commit()
        scan_id, image_name = scan.id, scan.image_name

    path = config.RECEIPTS_DIR / image_name
    text_path = path.with_suffix(".txt")
    outcome: ReceiptResult | Exception
    try:
        if text_path.is_file():
            result = scanner.scan_text(text_path.read_text(encoding="utf-8"))
        else:
            result = scanner.scan(path.read_bytes())
        outcome = check_totals(result)
    except FileNotFoundError:
        outcome = ScanFailed("The receipt image is missing")
    except (ScannerUnavailable, ScanFailed) as e:
        outcome = e
    except Exception as e:
        log.exception("Receipt scan %d crashed", scan_id)
        outcome = ScanFailed(f"Unexpected error: {type(e).__name__}")

    with session_factory() as db:
        scan = db.get(models.ReceiptScan, scan_id)
        if scan is None or scan.status != "processing":
            # Deleted by its owner while the scanner was reading it.
            return not isinstance(outcome, ScannerUnavailable)
        if isinstance(outcome, ReceiptResult):
            scan.status = "done"
            scan.result_json = outcome.model_dump_json()
            scan.error = None
            scan.model = config.RECEIPT_SCANNER_MODEL
            log.info("Receipt scan %d done", scan_id)
        elif isinstance(outcome, ScannerUnavailable):
            scan.status = "queued"
            level = (
                logging.WARNING
                if isinstance(outcome, ScannerMisconfigured)
                else logging.INFO
            )
            log.log(
                level,
                "Receipt scan %d postponed: scanner unavailable (%s)",
                scan_id,
                outcome,
            )
        else:
            scan.attempts += 1
            scan.error = str(outcome)
            scan.status = "failed" if scan.attempts >= MAX_ATTEMPTS else "queued"
            log.warning(
                "Receipt scan %d attempt %d failed: %s", scan_id, scan.attempts, outcome
            )
        db.commit()
    return not isinstance(outcome, ScannerUnavailable)


async def run(session_factory: sessionmaker, scanner=None) -> None:
    scanner = scanner or OpenAICompatibleScanner()
    await asyncio.to_thread(reset_stuck, session_factory)
    backoff = _BACKOFF_START
    while True:
        try:
            if not await asyncio.to_thread(has_queued, session_factory):
                await asyncio.sleep(_IDLE_SECONDS)
                continue
            reachable = await asyncio.to_thread(scanner.reachable)
            status.record(reachable)
            if reachable and await asyncio.to_thread(
                process_next, session_factory, scanner
            ):
                backoff = _BACKOFF_START
                continue
            status.record(False)
            log.info("Receipt scanner unavailable, next try in %d s", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _BACKOFF_MAX)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Receipt worker error")
            # A failed write can leave the scan in `processing`; this worker is the only one.
            with contextlib.suppress(Exception):
                await asyncio.to_thread(reset_stuck, session_factory)
            await asyncio.sleep(_BACKOFF_START)
