from enum import Enum

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import get_current_user, get_db

router = APIRouter()


def _build_pairwise(db: Session):
    users = db.query(models.User).all()
    balances = {u.id: {u1.id: 0.0 for u1 in users if u1.id != u.id} for u in users}

    for expense in db.query(models.Expense).all():
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
                # balances[A][B] < 0 means A owes B
                balances[debtor.user_id][payer.user_id] -= portion
                balances[payer.user_id][debtor.user_id] += portion

    return users, balances


def _full_settlements(users, balances):
    user_map = {u.id: u.name for u in users}
    seen = set()
    result = []

    for a_id in sorted(user_map):
        for b_id in sorted(user_map):
            if a_id >= b_id:
                continue
            pair = (a_id, b_id)
            if pair in seen:
                continue
            seen.add(pair)

            val = balances[a_id].get(b_id, 0.0)
            if val < -0.005:
                result.append(schemas.SettlementRead(
                    from_user_id=a_id, from_name=user_map[a_id],
                    to_user_id=b_id, to_name=user_map[b_id],
                    amount=round(-val, 2),
                ))
            elif val > 0.005:
                result.append(schemas.SettlementRead(
                    from_user_id=b_id, from_name=user_map[b_id],
                    to_user_id=a_id, to_name=user_map[a_id],
                    amount=round(val, 2),
                ))

    return sorted(result, key=lambda s: (s.from_name, s.to_name))


def _simplified_settlements(users, balances):
    user_map = {u.id: u.name for u in users}
    net = {u.id: sum(balances[u.id].values()) for u in users}

    debtors = sorted(
        [[-v, uid] for uid, v in net.items() if v < -0.005],
        key=lambda x: -x[0],
    )
    creditors = sorted(
        [[v, uid] for uid, v in net.items() if v > 0.005],
        key=lambda x: -x[0],
    )

    result = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        debt, d_id = debtors[i]
        credit, c_id = creditors[j]
        payment = round(min(debt, credit), 2)
        result.append(schemas.SettlementRead(
            from_user_id=d_id, from_name=user_map[d_id],
            to_user_id=c_id, to_name=user_map[c_id],
            amount=payment,
        ))
        debtors[i][0] -= payment
        creditors[j][0] -= payment
        if debtors[i][0] < 0.005:
            i += 1
        if creditors[j][0] < 0.005:
            j += 1

    return result


class SettlementMode(str, Enum):
    simplified = "simplified"
    full = "full"


@router.get("/", response_model=list[schemas.BalanceRead])
def get_balances(
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    users, balances = _build_pairwise(db)
    return [
        schemas.BalanceRead(
            user_id=u.id,
            name=u.name,
            balance=round(sum(balances[u.id].values()), 2),
        )
        for u in users
    ]


@router.get("/settlements/", response_model=list[schemas.SettlementRead])
def get_settlements(
    mode: SettlementMode = Query(default=SettlementMode.simplified),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    users, balances = _build_pairwise(db)
    if mode == SettlementMode.full:
        return _full_settlements(users, balances)
    return _simplified_settlements(users, balances)
