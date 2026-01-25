from __future__ import annotations
import pandas as pd
import matplotlib.pyplot as plt


class Expense:
    def __init__(self, date: pd.Timestamp, description: str, category: str, cost: float, currency: str, shares: dict[Person, float]):
        self.date = date
        self.description = description
        self.category = category
        self.cost = cost
        self.currency = currency
        self.shares = shares

    
    def __str__(self):
        return f"{self.date.strftime('%d.%m.%Y')} - {self.description}: {self.cost} {self.currency} ({self.shares})"


class ExpenseExtended(Expense):
    def __init__(self, date: pd.Timestamp, description: str, category: str, cost: float, currency: str, shares: dict[Person, float], comment: str = ""):
        super().__init__(date, description, category, cost, currency, shares)
        self.comment = comment

    def __str__(self):
        return super().__str__() + (f" - Comment: {self.comment}" if self.comment else "")


class Person:
    def __init__(self, name: str):
        self.name = name
        self.balance: dict[Person, float] = {}

    def __str__(self):
        return f"Person: {self.name}" + f", Balance: {self.balance}"


class Manager:
    def __init__(self, file_path: str = None):
        self.people = {}
        self.expenses = []

        if file_path:
            self._init_data(file_path)
            self.load_expenses(file_path)

    def _init_data(self, file_path: str):
        df = pd.read_csv(file_path)
        if "Comment" in df.columns:
            for person_name in df.columns[6:]:
                self.people[person_name] = Person(person_name)
        else:
            for person_name in df.columns[5:]:
                self.people[person_name] = Person(person_name)
    
    def load_expenses(self, file_path: str):
        df = pd.read_csv(file_path)
        for _, row in df.iterrows():
            if _ == len(df) - 1:
                break
            date = pd.to_datetime(row['Datum' if 'Datum' in row else 'Date'])
            description = row['Beschreibung' if 'Beschreibung' in row else 'Description']
            category = row['Kategorie' if 'Kategorie' in row else 'Category']
            cost = float(row['Kosten' if 'Kosten' in row else 'Cost'])
            currency = row['Währung' if 'Währung' in row else 'Currency']
            shares = {person: float(row[person]) for person in self.people.keys()}
            if "Comment" in row:
                comment = row["Comment"]
                expense = ExpenseExtended(date, description, category, cost, currency, shares, comment)
            else:
                expense = Expense(date, description, category, cost, currency, shares)

            self.expenses.append(expense)

            for p, s in shares.items():
                if s > 0:
                    for p2, s2 in shares.items():
                        if p != p2 and s2 < 0:
                            self.people[p].balance[p2] = self.people[p].balance.get(p2, 0) + s
                            self.people[p2].balance[p] = self.people[p2].balance.get(p, 0) - s

    def get_expenses(self) -> list[Expense]:
        return self.expenses

    def get_expenses_for_day(self, day: int, month: int, year: int) -> list[Expense]:
        return [expense for expense in self.expenses if expense.date.day == day and expense.date.month == month and expense.date.year == year]

    def get_expenses_for_month(self, month: int, year: int) -> list[Expense]:
        return [expense for expense in self.expenses if expense.date.month == month and expense.date.year == year]
    
    def get_expenses_for_year(self, year: int) -> list[Expense]:
        return [expense for expense in self.expenses if expense.date.year == year]

    def amount_spend(self, expenses: list[Expense]=None) -> float:
        expenses = expenses if expenses is not None else self.expenses
        return round(sum(expense.cost for expense in expenses if expense.category != "Zahlung"), 2)
    
    def expenses_to_dataframe(self, expenses: list[Expense]=None) -> pd.DataFrame:
        expenses = expenses if expenses is not None else self.expenses
        rows = []
        for expense in expenses:
            row = {
                "Date": pd.to_datetime(expense.date),
                "Description": expense.description,
                "Category": expense.category,
                "Cost": expense.cost,
                "Currency": expense.currency,
            }
            if isinstance(expense, ExpenseExtended):
                row["Comment"] = expense.comment
            for name in self.people.keys():
                row[name] = expense.shares.get(name, 0)
            rows.append(row)
        df = pd.DataFrame(rows)
        for col in df.columns:
            if col in ["Description", "Category", "Currency", "Comment"]:
                df[col] = df[col].astype("string")
        return df

    def get_person(self, name: str) -> Person:
        return self.people.get(name)
    

    def __str__(self):
        return "\n".join(str(expense) for expense in self.expenses) + "\n\n" + "\n".join(str(person) for person in self.people.values())
    
        

if __name__ == "__main__":
    """manager = Manager("Splitwise expenses Dec 26.csv")
    df = manager.expenses_to_dataframe()
    df["Comment"] = ""
    df.loc[(df["Date"] == "2025-12-16") & (df["Description"] == "Tierarzt "), "Comment"] = "Meine Mutter hat uns 50€ zu den Kosten dazu gegeben"
    df = df[["Date", "Description", "Category", "Cost", "Currency", "Comment", "Tom Hammel", "Nicola Becker"]]
    df.to_csv("expenses_exported.csv", index=False)"""
    manager = Manager("Splitwise expenses Jan 2.csv")
    print(manager)