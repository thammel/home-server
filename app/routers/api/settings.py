from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import get_current_user, get_db

router = APIRouter()


@router.get("/", response_model=schemas.SettingsRead)
def get_settings(
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    row = db.query(models.AppSetting).filter_by(key="settlement_mode").first()
    return schemas.SettingsRead(settlement_mode=row.value if row else "simplified")


@router.patch("/", response_model=schemas.SettingsRead)
def update_settings(
    payload: schemas.SettingsUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    if payload.settlement_mode not in ("simplified", "full"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid mode")
    row = db.query(models.AppSetting).filter_by(key="settlement_mode").first()
    if row is None:
        row = models.AppSetting(key="settlement_mode", value=payload.settlement_mode)
        db.add(row)
    else:
        row.value = payload.settlement_mode
    db.commit()
    return schemas.SettingsRead(settlement_mode=row.value)
