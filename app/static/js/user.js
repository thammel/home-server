import {api} from "./api.js";

const userId = parseInt(window.location.pathname.split("/").pop());

window.onload = async () => {
    const users = await api.getUsers();
    const balances = await api.getBalances();
    const expenses = await api.getExpenses();

    const user = users.find(u => u.id === userId);
    const balance = balances.find(b => b.user_id === userId);

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

        const shareAmount = e.shares.find(s => s.user_id === userId)?.share || 0;
        const shareText = shareAmount > 0 ? ` (Share: ${shareAmount}€)` : ` (Share: ${-shareAmount}€)`;

        li.textContent = `${date.toLocaleDateString()} - ${description} [${category}]`;
        li.textContent += comment ? ` - ${comment}` : "";
        li.textContent += ` - ${cost}€${shareText}`;

        if (shareAmount < 0) {
            li.style.color = "green";
        } else if (shareAmount > 0) {
            li.style.color = "red";
        } else {
            li.style.color = "black";
        }

        const link = `/expenses/${e.id}/?next=/users/${userId}`;
        li.innerHTML = `<a href="${link}">${li.textContent}</a>`;

        expenses_list.appendChild(li);
    }
}
