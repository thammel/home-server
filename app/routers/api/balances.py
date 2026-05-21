from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import get_current_user, get_db

router = APIRouter()


@router.get("/", response_model=list[schemas.BalanceRead])
def get_balances(
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    users = db.query(models.User).all()
    balances = {u.id: {u1.id: 0.0 for u1 in users if u1.id != u.id} for u in users}

    expenses = db.query(models.Expense).all()
    for expense in expenses:
        payers = [s for s in expense.shares if s.share < 0]
        debtors = [s for s in expense.shares if s.share > 0]
        total_paid = sum(-s.share for s in payers)

        if total_paid <= 0:
            continue

        for debtor in debtors:
            for payer in payers:
                if debtor.user_id == payer.user_id:
                    continue
                portion = debtor.share * (-payer.share / total_paid)
                # This does it differently then Splitwise
                # Splitwise does only keep track of owed amounts
                balances[debtor.user_id][payer.user_id] -= portion
                balances[payer.user_id][debtor.user_id] += portion

    all_balances = [
        schemas.BalanceRead(
            user_id=u.id,
            name=u.name,
            balance=round(sum(balances[u.id].values()), 2)
        )
        for u in users
    ]
    return all_balances
