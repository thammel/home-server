from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.database import engine, SessionLocal
from app import models
from app.auth import hash_password
from app.routers.api import users, expenses, balances, auth, settings as settings_router

models.Base.metadata.create_all(bind=engine)


def _seed_admin():
    db = SessionLocal()
    try:
        if not db.query(models.User).first():
            db.add(models.User(
                name="admin",
                password_hash=hash_password("changeme"),
                is_admin=True,
            ))
            db.commit()
        if not db.query(models.AppSetting).filter_by(key="settlement_mode").first():
            db.add(models.AppSetting(key="settlement_mode", value="simplified"))
            db.commit()
    finally:
        db.close()


_seed_admin()

app = FastAPI(title="Flat Expenses")

app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(expenses.router, prefix="/api/expenses", tags=["Expenses"])
app.include_router(balances.router, prefix="/api/balances", tags=["Balances"])
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["Settings"])

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
def root():
    return FileResponse("app/static/index.html")


@app.get("/users/{user_id}")
def user_page(user_id: int):
    return FileResponse("app/static/user.html")


@app.get("/expenses")
def expenses_page():
    return FileResponse("app/static/expenses.html")

@app.get("/expenses/{expense_id}")
def expense_page(expense_id: int):
    return FileResponse("app/static/expense.html")


@app.get("/users/{user_id}/settings")
def settings_page(user_id: int):
    return FileResponse("app/static/settings.html")


@app.get("/admin")
def admin_page():
    return FileResponse("app/static/admin.html")
