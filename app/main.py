from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.database import engine
from app import models
from app.routers.api import users, expenses, balances, auth

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Flat Expenses")

app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(expenses.router, prefix="/api/expenses", tags=["Expenses"])
app.include_router(balances.router, prefix="/api/balances", tags=["Balances"])
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])

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
