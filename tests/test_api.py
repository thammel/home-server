import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base
from app.routers.api import balances, expenses, users


@pytest.fixture()
def client():
    _ = models
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    app = FastAPI()
    app.include_router(users.router, prefix="/api/users")
    app.include_router(expenses.router, prefix="/api/expenses")
    app.include_router(balances.router, prefix="/api/balances")

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[users.get_db] = override_get_db
    app.dependency_overrides[expenses.get_db] = override_get_db
    app.dependency_overrides[balances.get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client


def create_user(client: TestClient, name: str) -> int:
    res = client.post("/api/users/", json={"name": name})
    assert res.status_code == 200
    return res.json()["id"]


def test_create_and_list_users(client: TestClient):
    user_id = create_user(client, "Alice")

    res = client.get("/api/users/")
    assert res.status_code == 200
    data = res.json()

    assert len(data) == 1
    assert data[0]["id"] == user_id
    assert data[0]["name"] == "Alice"


def test_create_expense_valid_shares(client: TestClient):
    alice_id = create_user(client, "Alice")
    bob_id = create_user(client, "Bob")

    payload = {
        "date": "2026-01-01",
        "description": "Groceries",
        "category": "Food",
        "cost": 30.0,
        "currency": "EUR",
        "comment": "",
        "shares": [
            {"user_id": alice_id, "share": -30.0},
            {"user_id": bob_id, "share": 30.0},
        ],
    }

    res = client.post("/api/expenses/", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["cost"] == 30.0
    assert len(data["shares"]) == 2


def test_create_expense_invalid_shares(client: TestClient):
    alice_id = create_user(client, "Alice")
    bob_id = create_user(client, "Bob")

    payload = {
        "date": "2026-01-01",
        "description": "Dinner",
        "category": "Food",
        "cost": 25.0,
        "currency": "EUR",
        "comment": None,
        "shares": [
            {"user_id": alice_id, "share": -25.0},
            {"user_id": bob_id, "share": 20.0},
        ],
    }

    res = client.post("/api/expenses/", json=payload)
    assert res.status_code == 400


def test_balances_with_multiple_payers(client: TestClient):
    alice_id = create_user(client, "Alice")
    bob_id = create_user(client, "Bob")
    carol_id = create_user(client, "Carol")

    payload = {
        "date": "2026-01-02",
        "description": "Supplies",
        "category": "House",
        "cost": 30.0,
        "currency": "EUR",
        "comment": None,
        "shares": [
            {"user_id": alice_id, "share": -10.0},
            {"user_id": bob_id, "share": -20.0},
            {"user_id": carol_id, "share": 30.0},
        ],
    }

    res = client.post("/api/expenses/", json=payload)
    assert res.status_code == 201

    res = client.get("/api/balances/")
    assert res.status_code == 200
    balances_data = {b["name"]: b["balance"] for b in res.json()}

    assert balances_data["Alice"] == 10.0
    assert balances_data["Bob"] == 20.0
    assert balances_data["Carol"] == -30.0
