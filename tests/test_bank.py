"""Bank import (ADR 0007). The FinTS session is replaced by a fake: no test talks to a bank."""

import datetime
import logging
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import config, models
from app.auth import get_current_user, get_db, hash_password
from app.bank.fints_backend import (
    BankError,
    Challenge,
    FetchedAccount,
    FetchedTransaction,
    FetchResult,
)
from app.bank.syncs import registry
from app.database import Base
from app.routers.api import bank, expenses

PIN = "secret-pin-4711"
IBAN = "DE00123456780000000001"


def tx(
    day: int, amount: str, who="Shop", purpose="Card payment", reference=""
) -> FetchedTransaction:
    date = datetime.date(2026, 11, day)
    return FetchedTransaction(
        booking_date=date,
        value_date=date,
        amount=Decimal(amount),
        currency="EUR",
        counterparty=who,
        counterparty_iban="",
        purpose=purpose,
        reference=reference,
    )


def result(*transactions, iban=IBAN) -> FetchResult:
    return FetchResult(
        accounts=[
            FetchedAccount(iban=iban, name="Giro", transactions=list(transactions))
        ],
        state=b"state",
        tan_mechanism="900",
    )


class FakeBank:
    """Scripted outcomes: each start()/resume() pops the next one (FetchResult, Challenge or BankError)."""

    def __init__(self):
        self.script = []
        self.sessions = []

    def __call__(self, **kwargs):
        bank_ = self

        class Session:
            def __init__(self):
                self.kwargs = kwargs
                self.closed = False
                self.tans = []

            def _next(self):
                outcome = bank_.script.pop(0)
                if isinstance(outcome, BankError):
                    self.closed = True
                    raise outcome
                return outcome

            def start(self):
                return self._next()

            def resume(self, tan=""):
                self.tans.append(tan)
                return self._next()

            def close(self):
                self.closed = True

        session = Session()
        self.sessions.append(session)
        return session


@pytest.fixture()
def fake_bank(monkeypatch):
    fake = FakeBank()
    monkeypatch.setattr(bank, "session_factory", fake)
    monkeypatch.setattr(config, "FINTS_PRODUCT_ID", "TESTPRODUCT")
    registry.clear()
    yield fake
    registry.clear()


@pytest.fixture()
def flat():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = session_factory()
    people = [
        models.User(
            name="TestAdmin", password_hash=hash_password("testpass"), is_admin=True
        ),
        models.User(name="Anna", password_hash=hash_password("testpass")),
        models.User(name="Ben", password_hash=hash_password("testpass")),
    ]
    db.add_all(people)
    db.commit()
    ids = {u.name: u.id for u in people}
    db.close()

    def make_app(user_id):
        app = FastAPI()
        app.include_router(bank.router, prefix="/api/bank")
        app.include_router(expenses.router, prefix="/api/expenses")

        def override_get_db():
            s = session_factory()
            try:
                yield s
            finally:
                s.close()

        def override_user():
            with session_factory() as s:
                return s.get(models.User, user_id)

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_user
        return app

    with (
        TestClient(make_app(ids["TestAdmin"])) as admin,
        TestClient(make_app(ids["Anna"])) as anna,
        TestClient(make_app(ids["Ben"])) as ben,
    ):
        yield {
            "admin": admin,
            "anna": anna,
            "ben": ben,
            "ids": ids,
            "db": session_factory,
        }


def connect(client):
    res = client.put(
        "/api/bank/",
        json={
            "bank_code": "12345678",
            "server_url": "https://fints.example.test/",
            "login_name": "anna",
        },
    )
    assert res.status_code == 200, res.text
    return res.json()


def sync(client, **body):
    return client.post("/api/bank/sync", json={"pin": PIN, **body})


def transactions(client, status=None):
    return client.get(
        "/api/bank/transactions" + (f"?status={status}" if status else "")
    ).json()


def test_feature_off_without_product_id(flat, monkeypatch):
    monkeypatch.setattr(config, "FINTS_PRODUCT_ID", None)
    assert flat["anna"].get("/api/bank/").json()["enabled"] is False
    assert (
        flat["anna"]
        .put(
            "/api/bank/",
            json={
                "bank_code": "12345678",
                "server_url": "https://x.test/",
                "login_name": "a",
            },
        )
        .status_code
        == 404
    )


def test_admin_cannot_connect_a_bank(flat, fake_bank):
    assert flat["admin"].get("/api/bank/").json()["enabled"] is False
    assert (
        flat["admin"]
        .put(
            "/api/bank/",
            json={
                "bank_code": "12345678",
                "server_url": "https://x.test/",
                "login_name": "a",
            },
        )
        .status_code
        == 403
    )
    assert flat["admin"].get("/api/bank/transactions").status_code == 403


def test_connection_validation(flat, fake_bank):
    bad = [
        {"bank_code": "123", "server_url": "https://x.test/", "login_name": "a"},
        {"bank_code": "12345678", "server_url": "http://x.test/", "login_name": "a"},
    ]
    for body in bad:
        assert flat["anna"].put("/api/bank/", json=body).status_code == 422


def test_sync_imports_transactions_and_stores_state_but_not_pin(
    flat, fake_bank, caplog
):
    caplog.set_level(logging.DEBUG)
    connect(flat["anna"])
    fake_bank.script = [result(tx(3, "-12.50"), tx(4, "1500.00", who="Employer"))]
    res = sync(flat["anna"], since="2026-11-01")
    assert res.json() == {
        "status": "done",
        "new": 2,
        "known": 0,
        "sync_id": None,
        "challenge": None,
        "decoupled": None,
    }
    session = fake_bank.sessions[0]
    assert session.kwargs["pin"] == PIN and session.kwargs["since"] == datetime.date(
        2026, 11, 1
    )

    # Outgoing money waits for review, incoming money starts ignored.
    assert [t["amount"] for t in transactions(flat["anna"], "new")] == [-12.5]
    assert [t["amount"] for t in transactions(flat["anna"], "ignored")] == [1500.0]

    with flat["db"]() as db:
        connection = db.query(models.BankConnection).one()
        assert connection.fints_state == b"state" and connection.tan_mechanism == "900"
        dump = repr(
            [
                (c.name, getattr(connection, c.name))
                for c in models.BankConnection.__table__.columns
            ]
        )
        assert PIN not in dump
    assert PIN not in caplog.text
    assert PIN not in flat["anna"].get("/api/bank/").text


def test_overlapping_syncs_do_not_duplicate(flat, fake_bank):
    connect(flat["anna"])
    coffee = tx(5, "-4.50", who="Cafe")
    fake_bank.script = [
        result(coffee, coffee, tx(6, "-20")),
        result(coffee, coffee, tx(6, "-20"), tx(7, "-3")),
    ]
    assert sync(flat["anna"]).json()["new"] == 3
    second = sync(flat["anna"]).json()
    assert (second["new"], second["known"]) == (1, 3)
    assert len(transactions(flat["anna"])) == 4


def test_reference_is_used_and_placeholders_ignored(flat, fake_bank):
    connect(flat["anna"])
    a = tx(5, "-10", purpose="Order 1", reference="E2E-1")
    b = tx(5, "-10", purpose="Order 1 (text changed)", reference="E2E-1")
    fake_bank.script = [result(a), result(b)]
    sync(flat["anna"])
    assert sync(flat["anna"]).json()["known"] == 1


def test_default_since_overlaps_last_import(flat, fake_bank):
    connect(flat["anna"])
    assert flat["anna"].get("/api/bank/").json()["default_since"] == str(
        datetime.date.today() - datetime.timedelta(days=30)
    )
    fake_bank.script = [result(tx(20, "-1")), result()]
    sync(flat["anna"])
    assert flat["anna"].get("/api/bank/").json()["default_since"] == "2026-11-13"
    sync(flat["anna"])
    assert fake_bank.sessions[1].kwargs["since"] == datetime.date(2026, 11, 13)


def test_disabled_accounts_are_skipped(flat, fake_bank):
    connect(flat["anna"])
    fake_bank.script = [result(tx(3, "-1")), result()]
    sync(flat["anna"])
    account = flat["anna"].get("/api/bank/").json()["connection"]["accounts"][0]
    flat["anna"].patch(f"/api/bank/accounts/{account['id']}", json={"enabled": False})
    sync(flat["anna"])
    assert fake_bank.sessions[1].kwargs["skip_ibans"] == {IBAN}
    assert flat["anna"].get("/api/bank/transactions").json() == []
    assert flat["anna"].get("/api/bank/").json()["new_count"] == 0


def test_wrong_pin_is_reported_and_not_retried(flat, fake_bank):
    connect(flat["anna"])
    fake_bank.script = [BankError("pin", "Bank: 9931 PIN wrong")]
    res = sync(flat["anna"])
    assert res.status_code == 400 and "9931" in res.json()["detail"]
    assert len(fake_bank.sessions) == 1
    assert (
        flat["anna"].get("/api/bank/").json()["connection"]["last_error"]
        == "Bank: 9931 PIN wrong"
    )
    # The failed sync does not block the next one.
    fake_bank.script = [result()]
    assert sync(flat["anna"]).status_code == 200


def test_approval_flow(flat, fake_bank):
    connect(flat["anna"])
    fake_bank.script = [
        Challenge("Approve in your app", decoupled=True),
        Challenge("Still waiting", decoupled=True),
        result(tx(3, "-9")),
    ]
    first = sync(flat["anna"]).json()
    assert first["status"] == "approval" and first["decoupled"] is True
    # Another user cannot continue it.
    assert (
        flat["ben"]
        .post(f"/api/bank/sync/{first['sync_id']}/continue", json={})
        .status_code
        == 404
    )

    again = (
        flat["anna"].post(f"/api/bank/sync/{first['sync_id']}/continue", json={}).json()
    )
    assert again["status"] == "approval" and again["challenge"] == "Still waiting"
    done = (
        flat["anna"]
        .post(f"/api/bank/sync/{again['sync_id']}/continue", json={"tan": " 123456 "})
        .json()
    )
    assert done == {
        "status": "done",
        "new": 1,
        "known": 0,
        "sync_id": None,
        "challenge": None,
        "decoupled": None,
    }
    assert fake_bank.sessions[0].tans == ["", "123456"]
    assert (
        flat["anna"]
        .post(f"/api/bank/sync/{again['sync_id']}/continue", json={})
        .status_code
        == 404
    )


def test_parked_sync_expires_and_closes_the_session(flat, fake_bank):
    connect(flat["anna"])
    fake_bank.script = [Challenge("Approve", decoupled=True)]
    sync_id = sync(flat["anna"]).json()["sync_id"]
    registry.expire(sync_id)
    assert fake_bank.sessions[0].closed
    assert (
        flat["anna"].post(f"/api/bank/sync/{sync_id}/continue", json={}).status_code
        == 404
    )
    fake_bank.script = [result()]
    assert sync(flat["anna"]).status_code == 200


def test_new_sync_replaces_one_waiting_for_approval(flat, fake_bank):
    connect(flat["anna"])
    fake_bank.script = [Challenge("Approve", decoupled=True), result()]
    old_id = sync(flat["anna"]).json()["sync_id"]
    assert sync(flat["anna"]).status_code == 200
    assert fake_bank.sessions[0].closed
    assert flat["anna"].post(f"/api/bank/sync/{old_id}/continue", json={}).status_code == 404


def test_cancel_sync(flat, fake_bank):
    connect(flat["anna"])
    fake_bank.script = [Challenge("Approve", decoupled=True), result()]
    sync_id = sync(flat["anna"]).json()["sync_id"]
    assert flat["anna"].delete(f"/api/bank/sync/{sync_id}").status_code == 204
    assert fake_bank.sessions[0].closed
    assert sync(flat["anna"]).status_code == 200


def test_transactions_are_private(flat, fake_bank):
    connect(flat["anna"])
    fake_bank.script = [result(tx(3, "-9"))]
    sync(flat["anna"])
    tx_id = transactions(flat["anna"])[0]["id"]
    assert transactions(flat["ben"]) == []
    connect(flat["ben"])
    assert transactions(flat["ben"]) == []
    assert (
        flat["ben"]
        .patch(f"/api/bank/transactions/{tx_id}", json={"status": "ignored"})
        .status_code
        == 404
    )


def test_book_transaction_as_personal_expense_and_unlink_on_delete(flat, fake_bank):
    anna = flat["ids"]["Anna"]
    connect(flat["anna"])
    fake_bank.script = [result(tx(3, "-9.99", who="Bookshop"))]
    sync(flat["anna"])
    tx_id = transactions(flat["anna"])[0]["id"]

    expense = (
        flat["anna"]
        .post(
            "/api/expenses/",
            json={
                "date": "2026-11-03",
                "description": "Bookshop",
                "category": "Books",
                "cost": 9.99,
                "shares": [
                    {"user_id": anna, "share": -9.99},
                    {"user_id": anna, "share": 9.99},
                ],
            },
        )
        .json()
    )
    booked = (
        flat["anna"]
        .patch(f"/api/bank/transactions/{tx_id}", json={"expense_id": expense["id"]})
        .json()
    )
    assert (booked["status"], booked["expense_id"]) == ("booked", expense["id"])
    assert flat["anna"].get("/api/bank/").json()["new_count"] == 0

    flat["anna"].delete(f"/api/expenses/{expense['id']}")
    back = transactions(flat["anna"])[0]
    assert (back["status"], back["expense_id"]) == ("new", None)


def test_cannot_link_to_someone_elses_expense(flat, fake_bank):
    ben = flat["ids"]["Ben"]
    connect(flat["anna"])
    fake_bank.script = [result(tx(3, "-5"))]
    sync(flat["anna"])
    tx_id = transactions(flat["anna"])[0]["id"]
    bens = (
        flat["ben"]
        .post(
            "/api/expenses/",
            json={
                "date": "2026-11-03",
                "description": "x",
                "category": "x",
                "cost": 5,
                "shares": [{"user_id": ben, "share": -5}, {"user_id": ben, "share": 5}],
            },
        )
        .json()
    )
    assert (
        flat["anna"]
        .patch(f"/api/bank/transactions/{tx_id}", json={"expense_id": bens["id"]})
        .status_code
        == 400
    )


def test_possible_duplicate_hint(flat, fake_bank):
    anna, ben = flat["ids"]["Anna"], flat["ids"]["Ben"]
    hand = flat["anna"].post(
        "/api/expenses/",
        json={
            "date": "2026-11-02",
            "description": "Groceries",
            "category": "Food",
            "cost": 30,
            "shares": [
                {"user_id": anna, "share": -30},
                {"user_id": anna, "share": 15},
                {"user_id": ben, "share": 15},
            ],
        },
    )
    # Ben paid the same amount: not Anna's payment, so no hint from it.
    flat["ben"].post(
        "/api/expenses/",
        json={
            "date": "2026-11-04",
            "description": "Other",
            "category": "Food",
            "cost": 12,
            "shares": [{"user_id": ben, "share": -12}, {"user_id": anna, "share": 12}],
        },
    )
    connect(flat["anna"])
    fake_bank.script = [result(tx(4, "-30"), tx(4, "-12"), tx(20, "-30", who="Later"))]
    sync(flat["anna"])
    by_amount = {
        t["amount"]: t["possible_duplicate_expense_id"]
        for t in transactions(flat["anna"], "new")
        if t["booking_date"] == "2026-11-04"
    }
    assert by_amount == {-30.0: hand.json()["id"], -12.0: None}
    later = next(
        t
        for t in transactions(flat["anna"], "new")
        if t["booking_date"] == "2026-11-20"
    )
    assert later["possible_duplicate_expense_id"] is None


def test_delete_connection_removes_transactions_keeps_expenses(flat, fake_bank):
    anna = flat["ids"]["Anna"]
    connect(flat["anna"])
    fake_bank.script = [result(tx(3, "-2"))]
    sync(flat["anna"])
    expense = (
        flat["anna"]
        .post(
            "/api/expenses/",
            json={
                "date": "2026-11-03",
                "description": "x",
                "category": "x",
                "cost": 2,
                "shares": [
                    {"user_id": anna, "share": -2},
                    {"user_id": anna, "share": 2},
                ],
            },
        )
        .json()
    )
    flat["anna"].patch(
        f"/api/bank/transactions/{transactions(flat['anna'])[0]['id']}",
        json={"expense_id": expense["id"]},
    )
    assert flat["anna"].delete("/api/bank/").status_code == 204
    assert flat["anna"].get("/api/bank/").json()["connection"] is None
    with flat["db"]() as db:
        assert db.query(models.BankTransaction).count() == 0
    assert flat["anna"].get(f"/api/expenses/{expense['id']}").status_code == 200


def test_convert_mt940_transaction():
    from mt940.models import Amount, Date

    from app.bank.fints_backend import _convert

    converted = _convert({
        "date": Date(2026, 11, 2), "entry_date": Date(2026, 11, 3), "amount": Amount("12.50", "D", "EUR"),
        "applicant_name": "  Shop   GmbH ", "applicant_iban": "DE00 1234", "purpose": "Card\npayment",
        "end_to_end_reference": "NOTPROVIDED", "customer_reference": "NONREF", "bank_reference": None,
    })
    assert converted == FetchedTransaction(
        booking_date=datetime.date(2026, 11, 3), value_date=datetime.date(2026, 11, 2), amount=Decimal("-12.50"),
        currency="EUR", counterparty="Shop GmbH", counterparty_iban="DE001234", purpose="Card payment",
        reference="")
