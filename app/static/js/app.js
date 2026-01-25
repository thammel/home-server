import { api } from "./api.js";

window.onload = () => {
    loadBalances();
};


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

