"""Receipt scanning (ADR 0009). Scans are private to the uploader; admins have none (ADR 0001, 0006)."""

import io
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from app import config, models, schemas
from app.auth import get_current_user, get_db, utcnow
from app.receipts import scanner

router = APIRouter()
log = logging.getLogger("app.receipts")

_MAX_SIDE = 2000
_ACCEPTED_FORMATS = {"JPEG", "PNG"}
# A phone photo is about 12-50 MP; anything far beyond is a decompression bomb.
Image.MAX_IMAGE_PIXELS = 100_000_000


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
                raise HTTPException(
                    status_code=415, detail="Upload a JPEG or PNG photo"
                )
            # Lets the JPEG decoder skip detail we would scale away anyway; saves memory on small servers.
            image.draft("RGB", (_MAX_SIDE, _MAX_SIDE))
            image = ImageOps.exif_transpose(image)
            image = image.convert("RGB")
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError):
        raise HTTPException(
            status_code=415, detail="Upload a JPEG or PNG photo"
        ) from None
    image.thumbnail((_MAX_SIDE, _MAX_SIDE))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85)
    return out.getvalue()


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
    return schemas.ReceiptScanList(enabled=True, scans=[_read(s) for s in scans])


@router.post(
    "/", response_model=schemas.ReceiptScanRead, status_code=status.HTTP_201_CREATED
)
def upload(
    file: UploadFile,
    db: Session = Depends(get_db),
    user: models.User = Depends(_member),
):
    data = file.file.read(config.RECEIPT_MAX_BYTES + 1)
    if len(data) > config.RECEIPT_MAX_BYTES:
        raise HTTPException(status_code=413, detail="The photo is too large")
    jpeg = normalise_image(data)

    config.RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.jpg"
    target = config.RECEIPTS_DIR / name
    partial = target.with_suffix(".part")
    partial.write_bytes(jpeg)
    partial.replace(target)

    scan = models.ReceiptScan(
        uploaded_by=user.id,
        created_at=utcnow(),
        status="queued",
        image_name=name,
        attempts=0,
    )
    db.add(scan)
    try:
        db.commit()
    except Exception:
        target.unlink(missing_ok=True)
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


@router.delete("/{scan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scan(
    scan_id: int, db: Session = Depends(get_db), user: models.User = Depends(_member)
):
    scan = _own_scan(db, user, scan_id)
    name = scan.image_name
    db.delete(scan)
    db.commit()
    (config.RECEIPTS_DIR / name).unlink(missing_ok=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
