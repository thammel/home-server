"""Receipt scanning (ADR 0009). Scans are private to the uploader; admins have none (ADR 0001, 0006)."""

import io
import json
import logging
import uuid
from types import SimpleNamespace

import pypdfium2 as pdfium
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from app import config, models, schemas
from app.app_settings import get_setting
from app.auth import get_current_user, get_db, utcnow
from app.receipts import scanner, split, worker
from app.routers.api.expenses import validate_share_users

router = APIRouter()
log = logging.getLogger("app.receipts")

_MAX_SIDE = 2000
_ACCEPTED_FORMATS = {"JPEG", "PNG"}
_UNSUPPORTED = "Upload a JPEG or PNG photo or a PDF receipt"
# E-receipts are one or two pages; more is not a receipt.
_MAX_PDF_PAGES = 5
# Below this the PDF is a scan without a text layer; the photo path reads it instead.
_MIN_TEXT_CHARS = 20
# A phone photo is about 12-50 MP; anything far beyond is a decompression bomb.
_MAX_PIXELS = 60_000_000
# Unreviewed scans per user; each keeps a photo on disk.
MAX_OPEN_SCANS = 30
_OPEN = ("queued", "processing", "done", "failed")


def _enabled() -> bool:
    return scanner.configured()


def _member(user: models.User = Depends(get_current_user)) -> models.User:
    if user.is_admin:
        raise HTTPException(status_code=403, detail="Admins cannot scan receipts")
    if not _enabled():
        raise HTTPException(
            status_code=404, detail="Receipt scanning is not configured"
        )
    return user


def _read(scan: models.ReceiptScan) -> schemas.ReceiptScanRead:
    return schemas.ReceiptScanRead(
        id=scan.id,
        created_at=scan.created_at,
        status=scan.status,
        error=scan.error,
        attempts=scan.attempts,
        model=scan.model,
        expense_id=scan.expense_id,
        result=json.loads(scan.result_json) if scan.result_json else None,
    )


def _own_scan(db: Session, user: models.User, scan_id: int) -> models.ReceiptScan:
    scan = db.get(models.ReceiptScan, scan_id)
    if scan is None or scan.uploaded_by != user.id:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return scan


def normalise_image(data: bytes) -> bytes:
    """Upright, at most 2000 px on the long side, JPEG without EXIF (drops GPS position)."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in _ACCEPTED_FORMATS:
                raise HTTPException(status_code=415, detail=_UNSUPPORTED)
            # Checked before decoding: Pillow's own bomb guard only warns below 2x its limit.
            if image.width * image.height > _MAX_PIXELS:
                raise HTTPException(
                    status_code=413, detail="The photo has too many pixels"
                )
            # Lets the JPEG decoder skip detail we would scale away anyway; saves memory on small servers.
            image.draft("RGB", (_MAX_SIDE, _MAX_SIDE))
            image = ImageOps.exif_transpose(image)
            image = image.convert("RGB")
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError):
        raise HTTPException(status_code=415, detail=_UNSUPPORTED) from None
    return _to_jpeg(image)


def _to_jpeg(image: Image.Image) -> bytes:
    image.thumbnail((_MAX_SIDE, _MAX_SIDE))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85)
    return out.getvalue()


def read_pdf(data: bytes) -> tuple[bytes, str | None]:
    """First page as preview JPEG, plus the text of all pages (None for a scanned PDF)."""
    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError:
        raise HTTPException(status_code=415, detail=_UNSUPPORTED) from None
    try:
        if not 1 <= len(pdf) <= _MAX_PDF_PAGES:
            raise HTTPException(
                status_code=415,
                detail=f"A receipt PDF has at most {_MAX_PDF_PAGES} pages",
            )
        texts = []
        for page in pdf:
            textpage = page.get_textpage()
            texts.append(textpage.get_text_range())
            textpage.close()
        page = pdf[0]
        width, height = page.get_size()
        scale = min(_MAX_SIDE / max(width, height, 1), 4)
        preview = page.render(scale=scale).to_pil().convert("RGB")
    except pdfium.PdfiumError:
        raise HTTPException(status_code=415, detail=_UNSUPPORTED) from None
    finally:
        pdf.close()
    text = "\n".join(texts).replace("\r\n", "\n").strip()
    return _to_jpeg(preview), text if len(text) >= _MIN_TEXT_CHARS else None


def _write(target, data: bytes):
    partial = target.with_suffix(".part")
    partial.write_bytes(data)
    partial.replace(target)
    return target


@router.get("/", response_model=schemas.ReceiptScanList)
def list_scans(
    db: Session = Depends(get_db), user: models.User = Depends(get_current_user)
):
    if user.is_admin or not _enabled():
        return schemas.ReceiptScanList(enabled=False, scans=[])
    scans = (
        db.query(models.ReceiptScan)
        .filter(models.ReceiptScan.uploaded_by == user.id)
        .order_by(models.ReceiptScan.created_at.desc(), models.ReceiptScan.id.desc())
        .all()
    )
    return schemas.ReceiptScanList(
        enabled=True,
        scans=[_read(s) for s in scans],
        scanner_reachable=worker.status.reachable,
        scanner_last_reachable_at=worker.status.last_reachable_at,
    )


@router.post(
    "/", response_model=schemas.ReceiptScanRead, status_code=status.HTTP_201_CREATED
)
def upload(
    file: UploadFile,
    db: Session = Depends(get_db),
    user: models.User = Depends(_member),
):
    open_scans = (
        db.query(models.ReceiptScan)
        .filter(
            models.ReceiptScan.uploaded_by == user.id,
            models.ReceiptScan.status.in_(_OPEN),
        )
        .count()
    )
    if open_scans >= MAX_OPEN_SCANS:
        raise HTTPException(
            status_code=409,
            detail=f"{MAX_OPEN_SCANS} receipts are waiting. Save or discard some first.",
        )
    data = file.file.read(config.RECEIPT_MAX_BYTES + 1)
    if len(data) > config.RECEIPT_MAX_BYTES:
        raise HTTPException(status_code=413, detail="The photo is too large")
    if data.startswith(b"%PDF-"):
        jpeg, text = read_pdf(data)
    else:
        jpeg, text = normalise_image(data), None

    config.RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.jpg"
    target = config.RECEIPTS_DIR / name
    files = [target]
    if text is not None:
        # Written before the image so the worker never sees the image without its text.
        files.insert(0, target.with_suffix(".txt"))
    try:
        if text is not None:
            # A broken text layer can hold lone surrogates, which UTF-8 cannot encode.
            _write(files[0], text.encode("utf-8", "replace"))
        _write(target, jpeg)
        scan = models.ReceiptScan(
            uploaded_by=user.id,
            created_at=utcnow(),
            status="queued",
            image_name=name,
            attempts=0,
        )
        db.add(scan)
        db.commit()
    except Exception:
        for path in files:
            path.unlink(missing_ok=True)
            path.with_suffix(".part").unlink(missing_ok=True)
        raise
    db.refresh(scan)
    return _read(scan)


@router.get("/{scan_id}", response_model=schemas.ReceiptScanRead)
def get_scan(
    scan_id: int, db: Session = Depends(get_db), user: models.User = Depends(_member)
):
    return _read(_own_scan(db, user, scan_id))


@router.get("/{scan_id}/image")
def get_image(
    scan_id: int, db: Session = Depends(get_db), user: models.User = Depends(_member)
):
    scan = _own_scan(db, user, scan_id)
    path = config.RECEIPTS_DIR / scan.image_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Receipt image is gone")
    return FileResponse(
        path, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"}
    )


@router.post("/{scan_id}/accept", response_model=schemas.ReceiptScanRead)
def accept(
    scan_id: int,
    body: schemas.ReceiptAccept,
    db: Session = Depends(get_db),
    user: models.User = Depends(_member),
):
    """Link the expense the user saved from this scan."""
    scan = _own_scan(db, user, scan_id)
    if scan.status not in ("done", "failed"):
        raise HTTPException(
            status_code=409, detail="This receipt is not ready for review"
        )
    expense = db.get(models.Expense, body.expense_id)
    if expense is None or not any(s.user_id == user.id for s in expense.shares):
        raise HTTPException(status_code=404, detail="Expense not found")
    scan.status = "accepted"
    scan.expense_id = expense.id
    db.commit()
    return _read(scan)


def _expense_from_lines(
    user: models.User,
    body: schemas.ReceiptSplit,
    lines: list[schemas.ReceiptSplitLine],
    currency: str,
) -> models.Expense:
    cents = split.allocate((line.line_total, line.user_ids) for line in lines)
    total = sum(cents.values())
    if total <= 0:
        raise HTTPException(
            status_code=400, detail="The lines must add up to more than zero"
        )
    if any(c < 0 for c in cents.values()):
        raise HTTPException(
            status_code=400,
            detail="Someone's lines add up to less than zero. Give a discount to the people of its item.",
        )
    cost = total / 100
    return models.Expense(
        date=body.date,
        description=body.description,
        category=body.category,
        cost=cost,
        currency=currency,
        comment=body.comment or None,
        shares=[models.ExpenseShare(user_id=user.id, share=-cost)]
        + [
            models.ExpenseShare(user_id=user_id, share=c / 100)
            for user_id, c in sorted(cents.items())
            if c
        ],
        items=[
            models.ExpenseItem(
                position=position,
                name=line.name,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_total=line.line_total,
                users=[
                    models.ExpenseItemUser(user_id=u)
                    for u in sorted(set(line.user_ids))
                ],
            )
            for position, line in enumerate(lines)
        ],
    )


@router.post(
    "/{scan_id}/split",
    response_model=schemas.ReceiptSplitResult,
    status_code=status.HTTP_201_CREATED,
)
def split_scan(
    scan_id: int,
    body: schemas.ReceiptSplit,
    db: Session = Depends(get_db),
    user: models.User = Depends(_member),
):
    """Save the scan as an expense split by its lines; the uploader paid (ADR 0010)."""
    scan = _own_scan(db, user, scan_id)
    if scan.status not in ("done", "failed"):
        raise HTTPException(
            status_code=409, detail="This receipt is not ready for review"
        )
    people = {u for line in body.lines for u in line.user_ids}
    validate_share_users(db, [SimpleNamespace(user_id=u) for u in people])

    own = [line for line in body.lines if set(line.user_ids) == {user.id}]
    others = [line for line in body.lines if set(line.user_ids) != {user.id}]
    groups = [own, others] if body.private_own and own and others else [body.lines]
    currency = get_setting(db, "currency")
    created = [_expense_from_lines(user, body, lines, currency) for lines in groups]
    db.add_all(created)
    db.flush()
    scan.status = "accepted"
    # The shared expense, when there are two: deleting it puts the receipt back up for review.
    scan.expense_id = created[-1].id
    db.commit()
    return schemas.ReceiptSplitResult(
        expenses=[schemas.ExpenseRead.model_validate(e) for e in created]
    )


@router.post("/{scan_id}/retry", response_model=schemas.ReceiptScanRead)
def retry(
    scan_id: int, db: Session = Depends(get_db), user: models.User = Depends(_member)
):
    scan = _own_scan(db, user, scan_id)
    if scan.status != "failed":
        raise HTTPException(status_code=409, detail="Only a failed scan can be retried")
    scan.status = "queued"
    scan.attempts = 0
    scan.error = None
    db.commit()
    return _read(scan)


@router.delete("/{scan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scan(
    scan_id: int, db: Session = Depends(get_db), user: models.User = Depends(_member)
):
    scan = _own_scan(db, user, scan_id)
    name = scan.image_name
    db.delete(scan)
    db.commit()
    image = config.RECEIPTS_DIR / name
    image.unlink(missing_ok=True)
    image.with_suffix(".txt").unlink(missing_ok=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
