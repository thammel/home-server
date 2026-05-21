from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_DAYS,
    create_session,
    get_current_user,
    get_db,
    verify_password,
)

router = APIRouter()


@router.post("/login", response_model=schemas.UserRead)
def login(payload: schemas.LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.name == payload.name).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    session = create_session(db, user)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session.session_id,
        httponly=True,
        samesite="lax",
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
    )
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        session = (
            db.query(models.UserSession)
            .filter(models.UserSession.session_id == session_id)
            .first()
        )
        if session:
            db.delete(session)
            db.commit()

    response.delete_cookie(key=SESSION_COOKIE_NAME, httponly=True, samesite="lax")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
