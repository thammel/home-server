from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import get_current_user, get_db

router = APIRouter()


def validate_shares(shares, cost: float):
    total = sum(s.share for s in shares)
    total_positive = sum(s.share for s in shares if s.share > 0)
    total_negative = sum(s.share for s in shares if s.share < 0)

    if abs(total) > 0.01:
        raise HTTPException(status_code=400, detail="Shares must net to zero")
    if abs(total_positive - cost) > 0.01 or abs(total_negative + cost) > 0.01:
        raise HTTPException(status_code=400, detail="Positive and negative shares must match total amount")


@router.post("/", response_model=schemas.ExpenseRead, status_code=status.HTTP_201_CREATED,
             responses={400: {"description": "Invalid expense data"}})
def create_expense(
    expense: schemas.ExpenseCreate,
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    validate_shares(expense.shares, expense.cost)

    for share in expense.shares:
        if not db.query(models.User).filter(models.User.id == share.user_id).first():
            raise HTTPException(status_code=400, detail=f"User {share.user_id} not found")

    db_expense = models.Expense(
        date=expense.date,
        description=expense.description,
        category=expense.category,
        cost=expense.cost,
        currency=expense.currency,
        comment=expense.comment
    )
    db.add(db_expense)
    db.commit()
    db.refresh(db_expense)

    for share in expense.shares:
        db.add(models.ExpenseShare(
            expense_id=db_expense.id,
            user_id=share.user_id,
            share=share.share
        ))

    db.commit()
    db.refresh(db_expense)
    return db_expense


@router.patch("/{expense_id}", response_model=schemas.ExpenseRead, responses={400: {"description": "Invalid expense data"},
                                         404: {"description": "Expense not found"}})
def update_expense(
    expense_id: int,
    expense: schemas.ExpenseUpdate,
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    db_expense = db.query(models.Expense).filter(models.Expense.id == expense_id).first()
    if not db_expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    if not _current_user.is_admin and not any(s.user_id == _current_user.id and s.share < 0 for s in db_expense.shares):
        raise HTTPException(status_code=403, detail="Forbidden")

    new_cost = expense.cost if expense.cost is not None else db_expense.cost
    new_shares = expense.shares if expense.shares is not None else db_expense.shares

    if expense.shares is not None or expense.cost is not None:
        validate_shares(new_shares, new_cost)

    for field in ("date", "description", "category", "cost", "currency", "comment"):
        value = getattr(expense, field)
        if value is not None:
            setattr(db_expense, field, value)

    db.add(db_expense)
    db.commit()
    db.refresh(db_expense)

    if expense.shares is not None:
        for share in expense.shares:
            if not db.query(models.User).filter(models.User.id == share.user_id).first():
                raise HTTPException(status_code=400, detail=f"User {share.user_id} not found")
        db.query(models.ExpenseShare).filter(models.ExpenseShare.expense_id == expense_id).delete()
        for share in expense.shares:
            db.add(models.ExpenseShare(
                expense_id=expense_id,
                user_id=share.user_id,
                share=share.share
            ))
        db.commit()
        db.refresh(db_expense)

    return db_expense


@router.get("/", response_model=list[schemas.ExpenseRead])
def list_expenses(
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.Expense)
    if not _current_user.is_admin:
        query = query.join(models.ExpenseShare).filter(models.ExpenseShare.user_id == _current_user.id)
    return query.all()


@router.get("/categories", response_model=list[str])
def list_categories(
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.Expense.category).distinct()
    if not _current_user.is_admin:
        query = query.join(models.ExpenseShare).filter(models.ExpenseShare.user_id == _current_user.id)
    results = query.all()
    return sorted(r[0] for r in results if r[0])


@router.get("/{expense_id}", response_model=schemas.ExpenseRead, responses={404: {"description": "Expense not found"}})
def get_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    expense = db.query(models.Expense).filter(models.Expense.id == expense_id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    if not _current_user.is_admin and not any(s.user_id == _current_user.id for s in expense.shares):
        raise HTTPException(status_code=403, detail="Forbidden")
    return expense


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT,
               responses={404: {"description": "Expense not found"}})
def delete_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    expense = db.query(models.Expense).filter(models.Expense.id == expense_id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    if not _current_user.is_admin and not any(s.user_id == _current_user.id and s.share < 0 for s in expense.shares):
        raise HTTPException(status_code=403, detail="Forbidden")
    db.delete(expense)
    db.commit()
    return None
