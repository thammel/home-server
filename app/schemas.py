from pydantic import BaseModel
from typing import List

class UserCreate(BaseModel):
    name: str

class UserRead(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True

class ExpenseShareCreate(BaseModel):
    user_id: int
    share_amount: float

class ExpenseCreate(BaseModel):
    description: str
    amount: float
    paid_by_id: int
    shares: List[ExpenseShareCreate]

class ExpenseShareRead(BaseModel):
    user_id: int
    share_amount: float

    class Config:
        from_attributes = True


class ExpenseRead(BaseModel):
    id: int
    description: str
    amount: float
    paid_by_id: int
    shares: List[ExpenseShareRead]

    class Config:
        from_attributes = True

class BalanceRead(BaseModel):
    user_id: int
    name: str
    balance: float
