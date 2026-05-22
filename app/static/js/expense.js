import { api, redirectToLogin, fmt } from "./api.js";

const expenseId = parseInt(window.location.pathname.split("/").pop());

window.onload = async () => {
    const params = new URLSearchParams(window.location.search);
    const next = params.get("next") || "/";
    const backLink = document.getElementById("back-link");
    if (backLink) backLink.href = next;

    let expense;
    try {
        expense = await api.getExpense(expenseId);
    } catch (err) {
        if (err.status === 401) {
            redirectToLogin();
            return;
        }
        if (err.status === 403) {
            document.getElementById("expense-title").textContent = "Not authorized";
            return;
        }
        throw err;
    }

    document.getElementById("expense-date").textContent = new Date(expense.date).toLocaleDateString();
    document.getElementById("expense-description").textContent = expense.description;
    document.getElementById("expense-category").textContent = expense.category;
    document.getElementById("expense-cost").textContent = `${fmt(expense.cost)} ${expense.currency}`;
    document.getElementById("expense-comment").textContent = expense.comment || "";

    const sharesList = document.getElementById("expense-shares");
    sharesList.innerHTML = "";

    expense.shares.forEach(s => {
        const li = document.createElement("li");
        li.textContent = `User ID: ${s.user_id}, Share: ${fmt(s.share)} ${expense.currency}`;
        sharesList.appendChild(li);
    });
};
