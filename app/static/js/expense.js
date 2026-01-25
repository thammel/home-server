import { api } from "./api.js";

const expenseId = parseInt(window.location.pathname.split("/").pop());

window.onload = async () => {
    const params = new URLSearchParams(window.location.search);
    const next = params.get("next") || "/";
    const backLink = document.getElementById("back-link");
    if (backLink) backLink.href = next;

    const expense = await api.getExpense(expenseId);

    document.getElementById("expense-date").textContent = new Date(expense.date).toLocaleDateString();
    document.getElementById("expense-description").textContent = expense.description;
    document.getElementById("expense-category").textContent = expense.category;
    document.getElementById("expense-cost").textContent = `${expense.cost} ${expense.currency}`;
    document.getElementById("expense-comment").textContent = expense.comment || "";

    const sharesList = document.getElementById("expense-shares");
    sharesList.innerHTML = "";

    expense.shares.forEach(s => {
        const li = document.createElement("li");
        li.textContent = `User ID: ${s.user_id}, Share: ${s.share} ${expense.currency}`;
        sharesList.appendChild(li);
    });
};