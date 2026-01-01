import { api } from "./api.js";

const userId = window.location.pathname.split("/").pop();

window.onload = async () => {
    const users = await api.getUsers();
    const balances = await api.getBalances();
    const expenses = await api.getExpenses();

    const user = users.find(u => u.id == userId);
    const balance = balances.find(b => b.user_id == userId);

    document.getElementById("username").textContent = user.name;
    document.getElementById("balance").textContent =
        balance.balance >= 0
            ? `Is owed €${balance.balance}`
            : `Owes €${-balance.balance}`;

    const paid = document.getElementById("paid");
    const owed = document.getElementById("owed");

    expenses.forEach(e => {
        if (e.paid_by_id == userId) {
            const li = document.createElement("li");
            li.textContent = `${e.description} (€${e.amount})`;
            paid.appendChild(li);
        }

        e.shares.forEach(s => {
            if (s.user_id == userId && e.paid_by_id != userId) {
                const li = document.createElement("li");
                li.textContent = `${e.description} (€${s.share_amount})`;
                owed.appendChild(li);
            }
        });
    });
};
