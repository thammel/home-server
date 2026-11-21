from sqlalchemy import Column, Integer, String, Float, ForeignKey, Date, DateTime, Boolean, LargeBinary, Text
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_admin = Column(Boolean, nullable=False, default=False)
    # Inactive users keep their expense history but cannot log in or be added to new expenses.
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    must_change_password = Column(Boolean, nullable=False, default=False, server_default="0")

    sessions = relationship("UserSession", back_populates="user", cascade="all, delete")


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)
    description = Column(String, nullable=False)
    category = Column(String, nullable=False)
    cost = Column(Float, nullable=False)
    currency = Column(String, nullable=False)
    comment = Column(String, nullable=True)

    shares = relationship("ExpenseShare", back_populates="expense", cascade="all, delete-orphan")

    @property
    def personal(self) -> bool:
        """All shares belong to one user (ADR 0005)."""
        return len({s.user_id for s in self.shares}) == 1


class ExpenseShare(Base):
    __tablename__ = "expense_shares"

    id = Column(Integer, primary_key=True, index=True)
    expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    share = Column(Float, nullable=False)

    expense = relationship("Expense", back_populates="shares")
    user = relationship("User")


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    user = relationship("User", back_populates="sessions")


class BankConnection(Base):
    """A user's FinTS login. Never holds the PIN (ADR 0007)."""

    __tablename__ = "bank_connections"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    bank_code = Column(String, nullable=False)
    server_url = Column(String, nullable=False)
    login_name = Column(String, nullable=False)
    # python-fints client state (bank parameters, system ID); no PIN, no account data.
    fints_state = Column(LargeBinary, nullable=True)
    tan_mechanism = Column(String, nullable=True)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)

    accounts = relationship("BankAccount", back_populates="connection", cascade="all, delete-orphan")


class BankAccount(Base):
    __tablename__ = "bank_accounts"

    id = Column(Integer, primary_key=True)
    connection_id = Column(Integer, ForeignKey("bank_connections.id"), nullable=False, index=True)
    iban = Column(String, nullable=False)
    name = Column(String, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)

    connection = relationship("BankConnection", back_populates="accounts")
    transactions = relationship("BankTransaction", back_populates="account", cascade="all, delete-orphan")


class BankTransaction(Base):
    __tablename__ = "bank_transactions"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False, index=True)
    booking_date = Column(Date, nullable=False)
    value_date = Column(Date, nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String, nullable=False)
    counterparty = Column(String, nullable=False, default="")
    counterparty_iban = Column(String, nullable=False, default="")
    purpose = Column(String, nullable=False, default="")
    dedupe_key = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default="new")
    expense_id = Column(Integer, ForeignKey("expenses.id", ondelete="SET NULL"), nullable=True)
    fetched_at = Column(DateTime(timezone=True), nullable=False)

    account = relationship("BankAccount", back_populates="transactions")


class ReceiptScan(Base):
    """An uploaded receipt waiting for, or read by, the scanner (ADR 0009). Private to the uploader."""

    __tablename__ = "receipt_scans"

    id = Column(Integer, primary_key=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    # queued -> processing -> done | failed, then accepted | discarded after review.
    status = Column(String, nullable=False, default="queued", index=True)
    # File name inside RECEIPTS_DIR, never a path from the client.
    image_name = Column(String, nullable=False)
    result_json = Column(Text, nullable=True)
    error = Column(String, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    model = Column(String, nullable=True)
    expense_id = Column(Integer, ForeignKey("expenses.id", ondelete="SET NULL"), nullable=True)
