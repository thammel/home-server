import { api, redirectToLogin, fmt } from "./api.js";

const userId = parseInt(window.location.pathname.split("/").pop());

window.onload = async () => {
    let currentUser;
    let settlements;
    let expenses;
    let settings;
    try {
        [currentUser, settings, expenses] = await Promise.all([api.getMe(), api.getSettings(), api.getExpenses()]);
        settlements = await api.getSettlements(settings.settlement_mode);
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

    document.getElementById("username").textContent = user.name;

    const settingsBtn = document.getElementById("settings-btn");
    if (currentUser.is_admin || currentUser.id === userId) {
        settingsBtn.style.display = "inline-block";
        settingsBtn.onclick = () => location.href = `/users/${userId}/settings`;
    }

    const balanceEl = document.getElementById("balance");
    const userSettlements = settlements.filter(s => s.from_user_id === user.id || s.to_user_id === user.id);

    if (userSettlements.length === 0) {
        balanceEl.textContent = "All settled up.";
    } else {
        const table = document.createElement("table");
        table.className = "borderless";
        table.style.width = "auto";
        table.style.minWidth = "16rem";
        table.style.margin = "0 auto";
        const tbody = document.createElement("tbody");
        for (const s of userSettlements) {
            const tr = document.createElement("tr");
            const isPaying = s.from_user_id === user.id;
            tr.style.color = isPaying ? "var(--pico-color-red-500)" : "var(--pico-color-green-500)";

            const labelTd = document.createElement("td");
            labelTd.textContent = isPaying ? `Pays ${s.to_name}` : `${s.from_name} pays`;

            const amountTd = document.createElement("td");
            amountTd.textContent = `€${fmt(s.amount)}`;
            amountTd.style.textAlign = "right";

            tr.append(labelTd, amountTd);
            tbody.appendChild(tr);
        }
        table.appendChild(tbody);
        balanceEl.appendChild(table);
    }

    const tbody = document.querySelector("#expenses tbody");
    tbody.innerHTML = "";

    expenses.sort((a, b) => new Date(b.date) - new Date(a.date));

    for (const e of expenses) {
        const date = new Date(e.date);
        const cost = Number(e.cost);
        const shareAmount = e.shares.find(s => s.user_id === user.id)?.share || 0;
        const link = `/expenses/${e.id}/?next=/users/${user.id}`;

        const tr = document.createElement("tr");
        tr.style.cursor = "pointer";
        tr.addEventListener("click", () => { window.location.href = link; });

        const dateTd = document.createElement("td");
        dateTd.textContent = date.toLocaleDateString();

        const descTd = document.createElement("td");
        descTd.textContent = e.description + (e.comment ? ` — ${e.comment}` : "");

        const catTd = document.createElement("td");
        catTd.textContent = e.category;

        const costTd = document.createElement("td");
        costTd.textContent = `€${fmt(cost)}`;

        const shareTd = document.createElement("td");
        if (shareAmount < 0) {
            shareTd.style.color = "var(--pico-color-green-500)";
            shareTd.textContent = `+€${fmt(-shareAmount)}`;
        } else if (shareAmount > 0) {
            shareTd.style.color = "var(--pico-color-red-500)";
            shareTd.textContent = `-€${fmt(shareAmount)}`;
        } else {
            shareTd.textContent = "—";
        }

        tr.append(dateTd, descTd, catTd, costTd, shareTd);
        tbody.appendChild(tr);
    }
}
