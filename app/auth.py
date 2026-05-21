import datetime
import secrets

from fastapi import Depends, HTTPException, Request, Response, status
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal

SESSION_COOKIE_NAME = "session_id"
SESSION_TTL_DAYS = 30

pwd_context = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_session(db: Session, user: models.User) -> models.UserSession:
    now = datetime.datetime.now(datetime.timezone.utc)
    expires_at = now + datetime.timedelta(days=SESSION_TTL_DAYS)
    session = models.UserSession(
        session_id=secrets.token_urlsafe(32),
        user_id=user.id,
        created_at=now,
        expires_at=expires_at,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_current_user(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> models.User:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    session = (
        db.query(models.UserSession)
        .filter(models.UserSession.session_id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    now = datetime.datetime.now(datetime.timezone.utc)
    if session.expires_at < now:
        db.delete(session)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    # Rolling session: extend expiry and refresh cookie.
    session.expires_at = now + datetime.timedelta(days=SESSION_TTL_DAYS)
    db.commit()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session.session_id,
        httponly=True,
        samesite="lax",
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
    )

    return session.user
