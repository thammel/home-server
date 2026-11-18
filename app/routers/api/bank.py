"""Bank import (ADR 0007). Every endpoint is scoped to the current user; admins have no bank data (ADR 0006)."""

import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import config, models, schemas
from app.auth import get_current_user, get_db, utcnow
from app.bank import importer
from app.bank.fints_backend import BankError, BankSession, Challenge
from app.bank.syncs import registry

router = APIRouter()
log = logging.getLogger("app.bank")

# Replaced in tests: nothing in CI talks to a bank.
session_factory = BankSession


def _enabled() -> bool:
    return bool(config.FINTS_PRODUCT_ID)


def _member(user: models.User = Depends(get_current_user)) -> models.User:
    if user.is_admin:
        raise HTTPException(
            status_code=403, detail="Admins cannot connect a bank account"
        )
    if not _enabled():
        raise HTTPException(status_code=404, detail="Bank import is not configured")
    return user


def _connection(db: Session, user: models.User) -> models.BankConnection | None:
    return (
        db.query(models.BankConnection)
        .filter(models.BankConnection.user_id == user.id)
        .first()
    )


def _connection_or_404(db: Session, user: models.User) -> models.BankConnection:
    connection = _connection(db, user)
    if connection is None:
        raise HTTPException(status_code=404, detail="No bank connected")
    return connection


def _own_transactions(db: Session, user: models.User):
    return (
        db.query(models.BankTransaction)
        .join(models.BankAccount)
        .join(models.BankConnection)
        .filter(models.BankConnection.user_id == user.id)
    )


def _visible_transactions(db: Session, user: models.User):
    """Lines of switched-off accounts stay stored but out of the way."""
    return _own_transactions(db, user).filter(models.BankAccount.enabled.is_(True))


@router.get("/", response_model=schemas.BankStatus)
def get_status(
    db: Session = Depends(get_db), user: models.User = Depends(get_current_user)
):
    if user.is_admin or not _enabled():
        return schemas.BankStatus(
            enabled=False, connection=None, new_count=0, default_since=None
        )
    connection = _connection(db, user)
    return schemas.BankStatus(
        enabled=True,
        connection=connection,
        new_count=_visible_transactions(db, user)
        .filter(models.BankTransaction.status == "new")
        .count(),
        default_since=importer.default_since(db, connection, datetime.date.today())
        if connection
        else None,
    )


@router.put("/", response_model=schemas.BankConnectionRead)
def save_connection(
    payload: schemas.BankConnectionWrite,
    db: Session = Depends(get_db),
    user: models.User = Depends(_member),
):
    connection = _connection(db, user)
    if connection is None:
        connection = models.BankConnection(
            user_id=user.id, created_at=utcnow(), **payload.model_dump()
        )
        db.add(connection)
    else:
        if registry.is_busy(user.id):
            raise HTTPException(status_code=409, detail="A sync is running")
        changed = (
            connection.bank_code,
            connection.server_url,
            connection.login_name,
        ) != (payload.bank_code, payload.server_url, payload.login_name)
        for key, value in payload.model_dump().items():
            setattr(connection, key, value)
        if changed:
            # Cached bank parameters belong to the old login.
            connection.fints_state = None
            connection.tan_mechanism = None
    db.commit()
    db.refresh(connection)
    return connection


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(
    db: Session = Depends(get_db), user: models.User = Depends(_member)
):
    """Remove the connection and all imported transactions. Expenses created from them stay."""
    connection = _connection_or_404(db, user)
    if registry.is_busy(user.id):
        raise HTTPException(status_code=409, detail="A sync is running")
    db.delete(connection)
    db.commit()


@router.patch("/accounts/{account_id}", response_model=schemas.BankAccountRead)
def update_account(
    account_id: int,
    payload: schemas.BankAccountUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(_member),
):
    connection = _connection_or_404(db, user)
    account = next((a for a in connection.accounts if a.id == account_id), None)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    account.enabled = payload.enabled
    db.commit()
    return account


def _fail(
    db: Session, connection: models.BankConnection, user: models.User, err: BankError
):
    registry.end(user.id)
    connection.last_error = str(err)
    db.commit()
    code = 400 if err.kind == "pin" else 502
    raise HTTPException(status_code=code, detail=str(err))


def _outcome(
    db: Session,
    connection: models.BankConnection,
    user: models.User,
    session,
    since,
    outcome,
):
    if isinstance(outcome, Challenge):
        sync_id = registry.park(user.id, session, since)
        return schemas.BankSyncResult(
            status="approval",
            sync_id=sync_id,
            challenge=outcome.text,
            decoupled=outcome.decoupled,
        )
    try:
        new, known = importer.store(db, connection, outcome)
        db.commit()
    finally:
        registry.end(user.id)
    return schemas.BankSyncResult(status="done", new=new, known=known)


@router.post(
    "/sync",
    response_model=schemas.BankSyncResult,
    responses={
        400: {"description": "Login rejected"},
        409: {"description": "Sync already running"},
        502: {"description": "Bank error"},
    },
)
def start_sync(
    payload: schemas.BankSyncStart,
    db: Session = Depends(get_db),
    user: models.User = Depends(_member),
):
    connection = _connection_or_404(db, user)
    if not payload.pin or len(payload.pin) > 100:
        raise HTTPException(status_code=400, detail="Enter your online banking PIN")
    today = datetime.date.today()
    since = payload.since or importer.default_since(db, connection, today)
    if since > today:
        raise HTTPException(status_code=400, detail="The start date is in the future")
    registry.drop_parked(user.id)
    if not registry.begin(user.id):
        raise HTTPException(status_code=409, detail="A sync is already running")
    try:
        session = session_factory(
            bank_code=connection.bank_code,
            server_url=connection.server_url,
            login_name=connection.login_name,
            pin=payload.pin,
            product_id=config.FINTS_PRODUCT_ID,
            state=connection.fints_state,
            tan_mechanism=connection.tan_mechanism,
            since=since,
            until=today,
            skip_ibans={a.iban for a in connection.accounts if not a.enabled},
        )
        outcome = session.start()
    except BankError as err:
        _fail(db, connection, user, err)
    except Exception:
        registry.end(user.id)
        log.exception("Bank sync failed")
        raise
    return _outcome(db, connection, user, session, since, outcome)


@router.post(
    "/sync/{sync_id}/continue",
    response_model=schemas.BankSyncResult,
    responses={404: {"description": "Sync expired or not found"}},
)
def continue_sync(
    sync_id: str,
    payload: schemas.BankSyncContinue,
    db: Session = Depends(get_db),
    user: models.User = Depends(_member),
):
    connection = _connection_or_404(db, user)
    pending = registry.take(sync_id, user.id)
    if pending is None:
        raise HTTPException(
            status_code=404, detail="This sync expired. Start it again."
        )
    try:
        outcome = pending.session.resume(payload.tan.strip())
    except BankError as err:
        _fail(db, connection, user, err)
    except Exception:
        pending.session.close()
        registry.end(user.id)
        log.exception("Bank sync failed")
        raise
    return _outcome(db, connection, user, pending.session, pending.since, outcome)


@router.delete("/sync/{sync_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_sync(sync_id: str, user: models.User = Depends(_member)):
    pending = registry.take(sync_id, user.id)
    if pending is not None:
        pending.session.close()
        registry.end(user.id)


@router.get("/transactions", response_model=list[schemas.BankTransactionRead])
def list_transactions(
    status_filter: str | None = Query(
        default=None, alias="status", pattern="^(new|booked|ignored)$"
    ),
    db: Session = Depends(get_db),
    user: models.User = Depends(_member),
):
    query = _visible_transactions(db, user)
    if status_filter:
        query = query.filter(models.BankTransaction.status == status_filter)
    rows = query.order_by(
        models.BankTransaction.booking_date, models.BankTransaction.id
    ).all()
    result = []
    for tx in rows:
        item = schemas.BankTransactionRead.model_validate(tx)
        if tx.status == "new":
            item.possible_duplicate_expense_id = importer.possible_duplicate(
                db, user.id, tx
            )
        result.append(item)
    return result


@router.patch("/transactions/{tx_id}", response_model=schemas.BankTransactionRead)
def update_transaction(
    tx_id: int,
    payload: schemas.BankTransactionUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(_member),
):
    tx = _own_transactions(db, user).filter(models.BankTransaction.id == tx_id).first()
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if payload.expense_id is not None:
        expense = db.get(models.Expense, payload.expense_id)
        if expense is None or not any(s.user_id == user.id for s in expense.shares):
            raise HTTPException(
                status_code=400, detail="Link only to an expense you take part in"
            )
        tx.expense_id = expense.id
        tx.status = "booked"
    elif payload.status is not None:
        tx.status = payload.status
        tx.expense_id = None
    db.commit()
    db.refresh(tx)
    return tx
