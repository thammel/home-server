from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import SessionLocal

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=list[schemas.BalanceRead])
def get_balances(db: Session = Depends(get_db)):
    users = db.query(models.User).all()
    balances = {u.id: 0.0 for u in users}

    expenses = db.query(models.Expense).all()
    for expense in expenses:
        balances[expense.paid_by_id] += expense.amount
        for share in expense.shares:
            balances[share.user_id] -= share.share_amount

    return [
        schemas.BalanceRead(
            user_id=u.id,
            name=u.name,
            balance=round(balances[u.id], 2)
        )
        for u in users
    ]
