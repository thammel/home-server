import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base
from app.auth import get_current_user, get_db, hash_password
from app.routers.api import auth, balances, expenses, users


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
    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(users.router, prefix="/api/users")
    app.include_router(expenses.router, prefix="/api/expenses")
    app.include_router(balances.router, prefix="/api/balances")

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    # Pre-create admin user that get_current_user will return
    test_db = TestingSessionLocal()
    admin = models.User(name="TestAdmin", password_hash=hash_password("testpass"), is_admin=True)
    test_db.add(admin)
    test_db.commit()
    test_db.refresh(admin)
    admin_id = admin.id
    test_db.close()

    def override_get_current_user():
        db = TestingSessionLocal()
        user = db.query(models.User).filter(models.User.id == admin_id).first()
        db.close()
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app) as test_client:
        yield test_client


def create_user(client: TestClient, name: str) -> int:
    res = client.post("/api/users/", json={"name": name, "password": "password123"})
    assert res.status_code == 201
    return res.json()["id"]


def test_create_and_list_users(client: TestClient):
    user_id = create_user(client, "Alice")

    res = client.get("/api/users/")
    assert res.status_code == 200
    data = res.json()

    names = [u["name"] for u in data]
    assert "Alice" in names
    alice = next(u for u in data if u["name"] == "Alice")
    assert alice["id"] == user_id


def test_first_user_is_not_admin(client: TestClient):
    # TestAdmin already exists so next user should not be admin
    user_id = create_user(client, "RegularUser")
    res = client.get(f"/api/users/{user_id}")
    assert res.status_code == 200
    assert res.json()["is_admin"] is False


def test_login_success(client: TestClient):
    create_user(client, "LoginUser")
    res = client.post("/api/auth/login", json={"name": "LoginUser", "password": "password123"})
    assert res.status_code == 200
    assert res.json()["name"] == "LoginUser"


def test_login_invalid_credentials(client: TestClient):
    create_user(client, "LoginUser2")
    res = client.post("/api/auth/login", json={"name": "LoginUser2", "password": "wrongpass"})
    assert res.status_code == 401


def test_logout(client: TestClient):
    create_user(client, "LogoutUser")
    login_res = client.post("/api/auth/login", json={"name": "LogoutUser", "password": "password123"})
    assert login_res.status_code == 200
    logout_res = client.post("/api/auth/logout")
    assert logout_res.status_code == 204


def test_rename_user_duplicate_returns_409(client: TestClient):
    create_user(client, "UserA")
    user_b_id = create_user(client, "UserB")
    res = client.patch(f"/api/users/{user_b_id}", params={"new_username": "UserA"})
    assert res.status_code == 409


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


def test_create_expense_invalid_user_id(client: TestClient):
    alice_id = create_user(client, "Alice")

    payload = {
        "date": "2026-01-01",
        "description": "Ghost Expense",
        "category": "Food",
        "cost": 10.0,
        "currency": "EUR",
        "comment": None,
        "shares": [
            {"user_id": alice_id, "share": -10.0},
            {"user_id": 99999, "share": 10.0},
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


def test_balances_pizza_cash_split(client: TestClient):
    p1_id = create_user(client, "Person 1")
    p2_id = create_user(client, "Person 2")
    p3_id = create_user(client, "Person 3")
    p4_id = create_user(client, "Person 4")
    p5_id = create_user(client, "Person 5")

    payload = {
        "date": "2026-01-03",
        "description": "Pizza",
        "category": "Food",
        "cost": 75.0,
        "currency": "EUR",
        "comment": None,
        "shares": [
            {"user_id": p1_id, "share": 10.0},
            {"user_id": p2_id, "share": 15.0},
            {"user_id": p3_id, "share": 15.0},
            {"user_id": p4_id, "share": 15.0},
            {"user_id": p5_id, "share": 20.0},
            {"user_id": p3_id, "share": -40.0},
            {"user_id": p5_id, "share": -35.0},
        ],
    }

    res = client.post("/api/expenses/", json=payload)
    assert res.status_code == 201

    res = client.get("/api/balances/")
    assert res.status_code == 200
    balances_data = {b["name"]: b["balance"] for b in res.json()}

    assert balances_data["Person 1"] == -10.0
    assert balances_data["Person 2"] == -15.0
    assert balances_data["Person 3"] == 25.0
    assert balances_data["Person 4"] == -15.0
    assert balances_data["Person 5"] == 15.0

    payload = {
        "date": "2026-01-04",
        "description": "Drinks",
        "category": "Food",
        "cost": 15.0,
        "currency": "EUR",
        "comment": None,
        "shares": [
            {"user_id": p2_id, "share": 10.0},
            {"user_id": p4_id, "share": 5.0},
            {"user_id": p2_id, "share": -15.0},
        ],
    }

    res = client.post("/api/expenses/", json=payload)
    assert res.status_code == 201

    res = client.get("/api/balances/")
    assert res.status_code == 200
    balances_data = {b["name"]: b["balance"] for b in res.json()}

    assert balances_data["Person 1"] == -10.0
    assert balances_data["Person 2"] == -10.0
    assert balances_data["Person 3"] == 25.0
    assert balances_data["Person 4"] == -20.0
    assert balances_data["Person 5"] == 15.0
