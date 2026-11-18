"""Store fetched bank transactions without duplicates, and spot ones already entered by hand."""

import datetime
import hashlib
from collections import Counter

from sqlalchemy.orm import Session

from app import models
from app.auth import utcnow
from app.bank.fints_backend import FetchedTransaction, FetchResult

DEFAULT_LOOKBACK_DAYS = 30
OVERLAP_DAYS = 7
DUPLICATE_WINDOW_DAYS = 3


def _cents(value) -> int:
    return round(float(value) * 100)


def dedupe_key(account_id: int, tx: FetchedTransaction, occurrence: int) -> str:
    """Stable per bank transaction, so overlapping fetches never import it twice.

    `occurrence` counts identical lines within one fetch: two real coffees of the same price
    on the same day stay two rows, a re-fetch of that day adds none.
    """
    if tx.reference:
        parts = [
            account_id,
            "ref",
            tx.reference,
            tx.booking_date,
            _cents(tx.amount),
            occurrence,
        ]
    else:
        parts = [
            account_id,
            tx.booking_date,
            _cents(tx.amount),
            tx.counterparty_iban or tx.counterparty,
            tx.purpose,
            occurrence,
        ]
    return hashlib.sha256("\x1f".join(map(str, parts)).encode()).hexdigest()


def default_since(
    db: Session, connection: models.BankConnection, today: datetime.date
) -> datetime.date:
    """Latest imported booking date minus an overlap for late bookings; first sync looks back 30 days."""
    latest = (
        db.query(models.BankTransaction.booking_date)
        .join(models.BankAccount)
        .filter(models.BankAccount.connection_id == connection.id)
        .order_by(models.BankTransaction.booking_date.desc())
        .limit(1)
        .scalar()
    )
    if latest is None:
        return today - datetime.timedelta(days=DEFAULT_LOOKBACK_DAYS)
    return latest - datetime.timedelta(days=OVERLAP_DAYS)


def store(
    db: Session, connection: models.BankConnection, result: FetchResult
) -> tuple[int, int]:
    """Save accounts and new transactions. Returns (new, already known)."""
    accounts = {a.iban: a for a in connection.accounts}
    new = known = 0
    now = utcnow()
    for fetched in result.accounts:
        account = accounts.get(fetched.iban)
        if account is None:
            account = models.BankAccount(
                iban=fetched.iban, name=fetched.name, enabled=True
            )
            connection.accounts.append(account)
            accounts[fetched.iban] = account
            db.flush()
        seen = Counter()
        keys = []
        for tx in fetched.transactions:
            base = dedupe_key(account.id, tx, 0)
            keys.append((dedupe_key(account.id, tx, seen[base]), tx))
            seen[base] += 1
        existing = {
            k
            for (k,) in db.query(models.BankTransaction.dedupe_key).filter(
                models.BankTransaction.dedupe_key.in_([k for k, _ in keys])
            )
        }
        for key, tx in keys:
            if key in existing:
                known += 1
                continue
            db.add(
                models.BankTransaction(
                    account_id=account.id,
                    booking_date=tx.booking_date,
                    value_date=tx.value_date,
                    amount=_cents(tx.amount) / 100,
                    currency=tx.currency,
                    counterparty=tx.counterparty,
                    counterparty_iban=tx.counterparty_iban,
                    purpose=tx.purpose,
                    dedupe_key=key,
                    # Money coming in is rarely a shared expense; it waits in the ignored list.
                    status="new" if tx.amount < 0 else "ignored",
                    fetched_at=now,
                )
            )
            existing.add(key)
            new += 1
    connection.fints_state = result.state
    connection.tan_mechanism = result.tan_mechanism or connection.tan_mechanism
    connection.last_sync_at = now
    connection.last_error = None
    return new, known


def possible_duplicate(
    db: Session, user_id: int, tx: models.BankTransaction
) -> int | None:
    """An expense the user paid with the same amount within a few days, not yet linked to a bank line."""
    if tx.amount >= 0:
        return None
    window = datetime.timedelta(days=DUPLICATE_WINDOW_DAYS)
    linked = db.query(models.BankTransaction.expense_id).filter(
        models.BankTransaction.expense_id.isnot(None)
    )
    candidates = (
        db.query(models.Expense)
        .join(models.ExpenseShare)
        .filter(
            models.ExpenseShare.user_id == user_id,
            models.ExpenseShare.share < 0,
            models.Expense.date.between(
                tx.booking_date - window, tx.booking_date + window
            ),
            models.Expense.id.not_in(linked),
        )
        .order_by(models.Expense.date)
        .all()
    )
    for expense in candidates:
        if _cents(expense.cost) == _cents(-tx.amount):
            return expense.id
    return None
