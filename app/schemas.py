import datetime

from pydantic import BaseModel, ConfigDict
from typing import List


class UserCreate(BaseModel):
    name: str


class UserRead(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class ExpenseShareCreate(BaseModel):
    user_id: int
    share: float


class ExpenseCreate(BaseModel):
    date: datetime.date
    description: str
    category: str
    cost: float
    currency: str
    comment: str | None
    shares: List[ExpenseShareCreate]


class ExpenseUpdate(BaseModel):
    date: datetime.date | None
    description: str | None
    category: str | None
    cost: float | None
    currency: str | None
    comment: str | None
    shares: List[ExpenseShareCreate] | None


class ExpenseShareRead(BaseModel):
    user_id: int
    share: float

    model_config = ConfigDict(from_attributes=True)


class ExpenseRead(BaseModel):
    id: int
    date: datetime.date
    description: str
    category: str
    cost: float
    currency: str
    comment: str | None
    shares: List[ExpenseShareRead]

    model_config = ConfigDict(from_attributes=True)


class BalanceRead(BaseModel):
    user_id: int
    name: str
    balance: float
