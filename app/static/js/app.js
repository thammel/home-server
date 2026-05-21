import { api } from "./api.js";

window.onload = () => {
    init();
};

async function init() {
    const loginSection = document.getElementById("login-section");
    const appSection = document.getElementById("app-section");
    const logoutButton = document.getElementById("logout-btn");
    const loginForm = document.getElementById("login-form");
    const loginError = document.getElementById("login-error");

    loginForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        loginError.textContent = "";

        const name = document.getElementById("login-name").value.trim();
        const password = document.getElementById("login-password").value;

        try {
            await api.login({ name, password });
            const params = new URLSearchParams(window.location.search);
            const next = params.get("next") || "/";
            window.location.href = next;
        } catch (err) {
            loginError.textContent = "Login failed. Check your name and password.";
        }
    });

    logoutButton.addEventListener("click", async () => {
        try {
            await api.logout();
        } finally {
            loginSection.style.display = "block";
            appSection.style.display = "none";
        }
    });

    try {
        await loadBalances();
        loginSection.style.display = "none";
        appSection.style.display = "block";
    } catch (err) {
        if (err.status !== 401) {
            loginError.textContent = "Failed to load balances.";
        }
        loginSection.style.display = "block";
        appSection.style.display = "none";
    }
}

async function loadBalances() {
    const balances = await api.getBalances();

    const ul = document.getElementById("balances");
    ul.innerHTML = "";

    balances.forEach(b => {
        const li = document.createElement("li");
        const a = document.createElement("a");
        a.href = `/users/${b.user_id}`;
        a.textContent = b.balance >= 0
            ? `${b.name} is owed €${b.balance}`
            : `${b.name} owes €${-b.balance}`;
        li.appendChild(a);
        ul.appendChild(li);
    });
}

