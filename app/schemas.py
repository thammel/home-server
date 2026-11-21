import datetime
import math
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, field_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Password = Annotated[str, StringConstraints(min_length=8, max_length=200)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Currency = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z]{3}$")]
Comment = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]
AppName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
SettlementMode = Literal["simplified", "full"]


def _round_money(value: float) -> float:
    return round(value, 2)


class UserCreate(BaseModel):
    name: Name
    password: Password


class UserRead(BaseModel):
    id: int
    name: str
    is_admin: bool
    is_active: bool
    must_change_password: bool

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    name: Name | None = None
    is_admin: bool | None = None
    is_active: bool | None = None
    password: Password | None = None
    # Required when users change their own password.
    current_password: str | None = None


class ExpenseShareCreate(BaseModel):
    user_id: int
    share: float

    @field_validator("share")
    @classmethod
    def _nonzero(cls, value: float) -> float:
        value = _round_money(value)
        if value == 0:
            raise ValueError("share must not be zero")
        return value


class ExpenseCreate(BaseModel):
    date: datetime.date
    description: ShortText
    category: ShortText
    cost: float = Field(gt=0)
    currency: Currency | None = None
    comment: Comment | None = None
    shares: list[ExpenseShareCreate] = Field(min_length=1)

    @field_validator("cost")
    @classmethod
    def _round_cost(cls, value: float) -> float:
        return _round_money(value)


class ExpenseUpdate(BaseModel):
    date: datetime.date | None = None
    description: ShortText | None = None
    category: ShortText | None = None
    cost: float | None = Field(default=None, gt=0)
    currency: Currency | None = None
    comment: Comment | None = None
    shares: list[ExpenseShareCreate] | None = Field(default=None, min_length=1)

    @field_validator("cost")
    @classmethod
    def _round_cost(cls, value: float | None) -> float | None:
        return None if value is None else _round_money(value)


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
    shares: list[ExpenseShareRead]
    personal: bool

    model_config = ConfigDict(from_attributes=True)


class ExpenseItemRead(BaseModel):
    name: str
    quantity: float
    unit_price: float | None
    line_total: float
    user_ids: list[int]

    model_config = ConfigDict(from_attributes=True)


class ExpenseDetail(ExpenseRead):
    items: list[ExpenseItemRead] = []
    # None without receipt lines; False when shares were edited after the receipt split (ADR 0010).
    items_match: bool | None = None


class BalanceRead(BaseModel):
    user_id: int
    name: str
    balance: float


class LoginRequest(BaseModel):
    name: str
    password: str


class SettlementRead(BaseModel):
    from_user_id: int
    from_name: str
    to_user_id: int
    to_name: str
    amount: float


class SettingsRead(BaseModel):
    app_name: str
    settlement_mode: SettlementMode
    currency: str


class SettingsUpdate(BaseModel):
    app_name: AppName | None = None
    settlement_mode: SettlementMode | None = None
    currency: Currency | None = None


class BankConnectionWrite(BaseModel):
    bank_code: str = Field(pattern=r"^\d{8}$", description="German bank code (BLZ)")
    server_url: str = Field(pattern=r"^https://\S+$", max_length=300, description="The bank's FinTS URL")
    login_name: str = Field(min_length=1, max_length=100)


class BankAccountRead(BaseModel):
    id: int
    iban: str
    name: str
    enabled: bool

    model_config = ConfigDict(from_attributes=True)


class BankAccountUpdate(BaseModel):
    enabled: bool


class BankConnectionRead(BaseModel):
    bank_code: str
    server_url: str
    login_name: str
    last_sync_at: datetime.datetime | None
    last_error: str | None
    accounts: list[BankAccountRead]

    model_config = ConfigDict(from_attributes=True)


class BankStatus(BaseModel):
    enabled: bool
    connection: BankConnectionRead | None
    new_count: int
    default_since: datetime.date | None


class BankSyncStart(BaseModel):
    # No length or format rules here: a validation error would echo the PIN back.
    pin: str
    since: datetime.date | None = None


class BankSyncContinue(BaseModel):
    tan: str = ""


class BankSyncResult(BaseModel):
    status: Literal["done", "approval"]
    new: int = 0
    known: int = 0
    sync_id: str | None = None
    challenge: str | None = None
    decoupled: bool | None = None


class BankTransactionRead(BaseModel):
    id: int
    account_id: int
    booking_date: datetime.date
    value_date: datetime.date | None
    amount: float
    currency: str
    counterparty: str
    counterparty_iban: str
    purpose: str
    status: str
    expense_id: int | None
    possible_duplicate_expense_id: int | None = None

    model_config = ConfigDict(from_attributes=True)


class BankCount(BaseModel):
    count: int


class BankTransactionUpdate(BaseModel):
    status: Literal["new", "ignored"] | None = None
    expense_id: int | None = None


class ReceiptItem(BaseModel):
    name: str
    quantity: float = 1
    unit_price: float | None = None
    line_total: float

    @field_validator("unit_price", "line_total")
    @classmethod
    def _round(cls, value: float | None) -> float | None:
        return None if value is None else _round_money(value)


class ReceiptResult(BaseModel):
    """What the scanner read. Lenient on purpose: the user reviews and fixes every field."""

    shop: str = ""
    date: datetime.date | None = None
    currency: str | None = None
    total: float
    items: list[ReceiptItem] = []
    warnings: list[str] = []

    @field_validator("date", mode="before")
    @classmethod
    def _date_or_none(cls, value):
        if isinstance(value, str):
            try:
                return datetime.date.fromisoformat(value.strip())
            except ValueError:
                return None
        return value

    @field_validator("currency", mode="before")
    @classmethod
    def _currency_code(cls, value):
        if isinstance(value, str) and len(value.strip()) == 3 and value.strip().isalpha():
            return value.strip().upper()
        return None

    @field_validator("total")
    @classmethod
    def _round_total(cls, value: float) -> float:
        return _round_money(value)


class ReceiptScanRead(BaseModel):
    id: int
    created_at: datetime.datetime
    status: str
    error: str | None
    attempts: int
    model: str | None
    expense_id: int | None
    result: dict | None = None


class ReceiptScanList(BaseModel):
    enabled: bool
    scans: list[ReceiptScanRead]
    # None until the worker has checked the scanner once since the last restart.
    scanner_reachable: bool | None = None
    scanner_last_reachable_at: datetime.datetime | None = None


class ReceiptAccept(BaseModel):
    expense_id: int


def _finite_or_text(value):
    # The 422 answer echoes the input; NaN or Infinity in it would make that answer a 500.
    if isinstance(value, float) and not math.isfinite(value):
        return "not a finite number"
    return value


LineAmount = Annotated[float, BeforeValidator(_finite_or_text), Field(ge=-1_000_000, le=1_000_000)]


class ReceiptSplitLine(BaseModel):
    name: ShortText
    quantity: Annotated[float, BeforeValidator(_finite_or_text)] = Field(default=1, gt=0, le=1_000_000)
    unit_price: LineAmount | None = None
    # Negative for discounts.
    line_total: LineAmount
    user_ids: list[int] = Field(min_length=1)

    @field_validator("unit_price", "line_total")
    @classmethod
    def _round(cls, value: float | None) -> float | None:
        return None if value is None else _round_money(value)


class ReceiptSplit(BaseModel):
    """Save a scan as expense(s) split by its lines (ADR 0010). The server derives the shares."""

    date: datetime.date
    description: ShortText
    category: ShortText
    comment: Comment | None = None
    # Lines that belong only to the uploader go into a separate personal expense.
    private_own: bool = False
    lines: list[ReceiptSplitLine] = Field(min_length=1, max_length=500)


class ReceiptSplitResult(BaseModel):
    expenses: list[ExpenseRead]
