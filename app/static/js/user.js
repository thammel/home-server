import { api, redirectToLogin } from "./api.js";

const userId = parseInt(window.location.pathname.split("/").pop());

window.onload = async () => {
    let currentUser;
    let balances;
    let expenses;
    try {
        currentUser = await api.getMe();
        balances = await api.getBalances();
        expenses = await api.getExpenses();
    } catch (err) {
        if (err.status === 401) {
            redirectToLogin();
            return;
        }
        if (err.status === 403) {
            document.getElementById("username").textContent = "Not authorized";
            return;
        }
        throw err;
    }

    if (!currentUser.is_admin && userId !== currentUser.id) {
        window.location.href = `/users/${currentUser.id}`;
        return;
    }

    let user = currentUser;
    if (currentUser.is_admin && userId !== currentUser.id) {
        user = await api.getUser(userId);
    }

    const balance = balances.find(b => b.user_id === user.id);

    document.getElementById("username").textContent = user.name;
    document.getElementById("balance").textContent =
        balance.balance >= 0
            ? `Is owed €${balance.balance}`
            : `Owes €${-balance.balance}`;

    const expenses_list = document.getElementById("expenses");
    expenses_list.innerHTML = "";

    expenses.sort((a, b) => {
        return new Date(b.date) - new Date(a.date);
    });

    for (const e of expenses) {
        const li = document.createElement("li");

        const rawDate = e.date
        const date = new Date(rawDate);

        const description = e.description;
        const category = e.category;
        const cost = Number(e.cost);
        const comment = e.comment || "";

        const shareAmount = e.shares.find(s => s.user_id === user.id)?.share || 0;
        const shareText = shareAmount > 0 ? ` (Share: ${shareAmount}€)` : ` (Share: ${-shareAmount}€)`;

        const text = `${date.toLocaleDateString()} - ${description} [${category}]`
            + (comment ? ` - ${comment}` : "")
            + ` - ${cost}€${shareText}`;

        if (shareAmount < 0) {
            li.style.color = "green";
        } else if (shareAmount > 0) {
            li.style.color = "red";
        } else {
            li.style.color = "black";
        }

        const link = `/expenses/${e.id}/?next=/users/${user.id}`;
        const a = document.createElement("a");
        a.href = link;
        a.textContent = text;
        li.appendChild(a);

        expenses_list.appendChild(li);
    }
}
