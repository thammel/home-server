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


def _make_app(session_factory, current_user_id: int) -> FastAPI:
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(users.router, prefix="/api/users")
    app.include_router(expenses.router, prefix="/api/expenses")
    app.include_router(balances.router, prefix="/api/balances")

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    def override_get_current_user():
        db = session_factory()
        user = db.query(models.User).filter(models.User.id == current_user_id).first()
        db.close()
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    return app


def _make_db():
    _ = models
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return session_factory


@pytest.fixture()
def client():
    session_factory = _make_db()
    db = session_factory()
    admin = models.User(name="TestAdmin", password_hash=hash_password("testpass"), is_admin=True)
    db.add(admin)
    db.commit()
    db.refresh(admin)
    admin_id = admin.id
    db.close()

    app = _make_app(session_factory, admin_id)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def non_admin_client():
    session_factory = _make_db()
    db = session_factory()
    admin = models.User(name="TestAdmin", password_hash=hash_password("testpass"), is_admin=True)
    regular = models.User(name="TestUser", password_hash=hash_password("testpass"), is_admin=False)
    db.add(admin)
    db.add(regular)
    db.commit()
    db.refresh(regular)
    regular_id = regular.id
    db.close()

    app = _make_app(session_factory, regular_id)
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


def test_new_user_is_not_admin(client: TestClient):
    user_id = create_user(client, "RegularUser")
    res = client.get(f"/api/users/{user_id}")
    assert res.status_code == 200
    assert res.json()["is_admin"] is False


def test_create_user_requires_admin(non_admin_client: TestClient):
    res = non_admin_client.post("/api/users/", json={"name": "NewUser", "password": "pass"})
    assert res.status_code == 403


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


def test_update_user_rename(client: TestClient):
    user_id = create_user(client, "UserA")
    res = client.patch(f"/api/users/{user_id}", json={"name": "UserA-renamed"})
    assert res.status_code == 200
    assert res.json()["name"] == "UserA-renamed"


def test_update_user_rename_duplicate_returns_409(client: TestClient):
    create_user(client, "UserA")
    user_b_id = create_user(client, "UserB")
    res = client.patch(f"/api/users/{user_b_id}", json={"name": "UserA"})
    assert res.status_code == 409


def test_update_user_toggle_admin(client: TestClient):
    user_id = create_user(client, "PromotedUser")
    res = client.patch(f"/api/users/{user_id}", json={"is_admin": True})
    assert res.status_code == 200
    assert res.json()["is_admin"] is True

    res = client.patch(f"/api/users/{user_id}", json={"is_admin": False})
    assert res.status_code == 200
    assert res.json()["is_admin"] is False


def test_update_user_toggle_admin_requires_admin(non_admin_client: TestClient):
    res = non_admin_client.patch("/api/users/1", json={"is_admin": True})
    assert res.status_code == 403


def test_delete_user(client: TestClient):
    user_id = create_user(client, "DeleteMe")
    res = client.delete(f"/api/users/{user_id}")
    assert res.status_code == 204

    res = client.get("/api/users/")
    names = [u["name"] for u in res.json()]
    assert "DeleteMe" not in names


def test_delete_user_requires_admin(non_admin_client: TestClient):
    res = non_admin_client.delete("/api/users/1")
    assert res.status_code == 403


def test_delete_self_forbidden(client: TestClient):
    res = client.get("/api/users/me")
    admin_id = res.json()["id"]
    res = client.delete(f"/api/users/{admin_id}")
    assert res.status_code == 403


def test_delete_last_admin_forbidden(client: TestClient):
    res = client.get("/api/users/me")
    admin_id = res.json()["id"]
    create_user(client, "NonAdmin")
    res = client.patch(f"/api/users/{admin_id}", json={"is_admin": False})
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


def test_get_categories_admin_sees_all(client: TestClient):
    alice_id = create_user(client, "Alice")
    bob_id = create_user(client, "Bob")

    for cat, payer, consumer in [("Food", alice_id, bob_id), ("House", bob_id, alice_id), ("Food", alice_id, bob_id)]:
        client.post("/api/expenses/", json={
            "date": "2026-01-01", "description": "x", "category": cat,
            "cost": 10.0, "currency": "EUR", "comment": None,
            "shares": [{"user_id": payer, "share": -10.0}, {"user_id": consumer, "share": 10.0}],
        })

    res = client.get("/api/expenses/categories")
    assert res.status_code == 200
    assert res.json() == ["Food", "House"]


def test_get_categories_non_admin_sees_own(non_admin_client: TestClient):
    me_id = non_admin_client.get("/api/users/me").json()["id"]
    all_users = non_admin_client.get("/api/users/").json()
    admin_id = next(u["id"] for u in all_users if u["id"] != me_id)

    # expense involving me → should appear in categories
    non_admin_client.post("/api/expenses/", json={
        "date": "2026-01-01", "description": "shared", "category": "Food",
        "cost": 20.0, "currency": "EUR", "comment": None,
        "shares": [{"user_id": admin_id, "share": -20.0}, {"user_id": me_id, "share": 20.0}],
    })
    # expense NOT involving me → should not appear
    non_admin_client.post("/api/expenses/", json={
        "date": "2026-01-01", "description": "admin only", "category": "Travel",
        "cost": 10.0, "currency": "EUR", "comment": None,
        "shares": [{"user_id": admin_id, "share": -10.0}, {"user_id": admin_id, "share": 10.0}],
    })

    res = non_admin_client.get("/api/expenses/categories")
    assert res.status_code == 200
    assert res.json() == ["Food"]


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
