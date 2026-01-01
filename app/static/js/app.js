import { api } from "./api.js";

window.onload = () => {
    loadUsers();
    loadBalances();
};

async function loadUsers() {
    const users = await api.getUsers();

    const paidBySelect = document.getElementById("paid_by");
    paidBySelect.innerHTML = "";

    users.forEach(u => {
        const option = document.createElement("option");
        option.value = u.id;
        option.textContent = u.name;
        paidBySelect.appendChild(option);
    });
}

async function loadBalances() {
    const balances = await api.getBalances();

    const ul = document.getElementById("balances");
    ul.innerHTML = "";

    balances.forEach(b => {
        const li = document.createElement("li");
        li.textContent =
            b.balance >= 0
                ? `${b.name} is owed €${b.balance}`
                : `${b.name} owes €${-b.balance}`;
        ul.appendChild(li);
        li.innerHTML = `<a href="/users/${b.user_id}">${li.textContent}</a>`;
    });
}

async function addExpense() {
    const description = document.getElementById("description").value;
    const amount = parseFloat(document.getElementById("amount").value);
    const paidById = parseInt(document.getElementById("paid_by").value);

    const users = await api.getUsers();

    const shareAmount = amount / users.length;

    const expense = {
        description: description,
        amount: amount,
        paid_by_id: paidById,
        shares: users.map(u => ({
            user_id: u.id,
            share_amount: shareAmount
        }))
    };

    await api.addExpense(expense);

    loadBalances();
}
