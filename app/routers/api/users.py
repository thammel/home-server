from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import get_current_user, get_db, hash_password

router = APIRouter()


@router.post(
    "/",
    response_model=schemas.UserRead,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "User name already exists"}},
)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    has_admin = db.query(models.User).filter(models.User.is_admin == True).first() is not None
    db_user = models.User(
        name=user.name,
        password_hash=hash_password(user.password),
        is_admin=not has_admin,
    )
    db.add(db_user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User name already exists",
        )
    db.refresh(db_user)
    return db_user


@router.get("/", response_model=list[schemas.UserRead])
def list_users(
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    return db.query(models.User).all()

@router.get("/me", response_model=schemas.UserRead)
def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.get(
    "/{user_id}",
    response_model=schemas.UserRead,
    responses={
        403: {"description": "Forbidden"},
        404: {"description": "User not found"},
    },
)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    if not _current_user.is_admin and _current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user

@router.patch(
    "/{user_id}",
    response_model=schemas.UserRead,
    responses={
        403: {"description": "Forbidden"},
        404: {"description": "User not found"},
    },
)
def rename_user(
    user_id: int,
    new_username: str,
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    if not _current_user.is_admin and _current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.name = new_username
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User name already exists",
        )
    db.refresh(user)
    return user


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"description": "Forbidden"},
        404: {"description": "User not found"},
    },
)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    if not _current_user.is_admin and _current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    db.query(models.ExpenseShare).filter(models.ExpenseShare.user_id == user_id).delete()
    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
