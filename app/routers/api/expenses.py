from fastapi import APIRouter, Depends, HTTPException
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

@router.post("/", response_model=schemas.ExpenseRead)
def create_expense(expense: schemas.ExpenseCreate, db: Session = Depends(get_db)):
    total = sum(s.share_amount for s in expense.shares)
    if abs(total - expense.amount) > 0.01:
        raise HTTPException(status_code=400, detail="Shares must sum to total amount")

    db_expense = models.Expense(
        description=expense.description,
        amount=expense.amount,
        paid_by_id=expense.paid_by_id
    )
    db.add(db_expense)
    db.commit()
    db.refresh(db_expense)

    for share in expense.shares:
        db.add(models.ExpenseShare(
            expense_id=db_expense.id,
            user_id=share.user_id,
            share_amount=share.share_amount
        ))

    db.commit()
    db.refresh(db_expense)
    return db_expense

@router.get("/", response_model=list[schemas.ExpenseRead])
def list_expenses(db: Session = Depends(get_db)):
    return db.query(models.Expense).all()
