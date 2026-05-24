import { api, fmt } from "./api.js";

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
            const user = await api.login({ name, password });
            document.getElementById("admin-btn").style.display = user.is_admin ? "inline-block" : "none";
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
        const me = await api.getMe();
        document.getElementById("admin-btn").style.display = me.is_admin ? "inline-block" : "none";
        document.getElementById("profile-btn").textContent = me.name;
        document.getElementById("profile-btn").onclick = () => location.href = `/users/${me.id}`;
        await loadSettlements(me.id, me.is_admin);
        loginSection.style.display = "none";
        appSection.style.display = "block";
    } catch (err) {
        if (err.status !== 401) {
            loginError.textContent = "Failed to load settlements.";
        }
        loginSection.style.display = "block";
        appSection.style.display = "none";
    }
}

async function loadSettlements(myId, isAdmin) {
    const settings = await api.getSettings();
    const settlements = await api.getSettlements(settings.settlement_mode);

    const container = document.getElementById("settlements-list");
    container.innerHTML = "";

    if (isAdmin) {
        renderAdminSettlements(container, settlements, myId);
    } else {
        const mine = settlements.filter(s => s.from_user_id === myId || s.to_user_id === myId);
        renderPersonalSettlements(container, mine, myId);
    }
}

function renderPersonalSettlements(container, userSettlements, myId) {
    if (userSettlements.length === 0) {
        container.textContent = "All settled up.";
        return;
    }

    const toPay = userSettlements.filter(s => s.from_user_id === myId);
    const toReceive = userSettlements.filter(s => s.to_user_id === myId);
    const totalOwed = toPay.reduce((sum, s) => sum + s.amount, 0);
    const totalReceive = toReceive.reduce((sum, s) => sum + s.amount, 0);
    const net = totalReceive - totalOwed;

    const summary = document.createElement("p");
    summary.style.fontWeight = "bold";
    summary.style.marginBottom = "0.5rem";
    if (Math.abs(net) < 0.005) {
        summary.textContent = "All settled up.";
        container.appendChild(summary);
        return;
    } else if (net > 0) {
        summary.style.color = "var(--pico-color-green-500)";
        summary.textContent = `You are owed €${fmt(net)} net`;
    } else {
        summary.style.color = "var(--pico-color-red-500)";
        summary.textContent = `You owe €${fmt(-net)} net`;
    }
    container.appendChild(summary);

    // compact flat list: payers first (red), then receivers (green)
    const table = document.createElement("table");
    table.className = "borderless";
    table.style.cssText = "width:auto;min-width:12rem;";
    const tbody = document.createElement("tbody");

    for (const s of toPay) {
        const tr = document.createElement("tr");
        const nameTd = Object.assign(document.createElement("td"), { textContent: s.to_name });
        nameTd.style.color = "var(--pico-color-red-500)";
        const amountTd = Object.assign(document.createElement("td"), { textContent: `−€${fmt(s.amount)}` });
        amountTd.style.color = "var(--pico-color-red-500)";
        amountTd.style.textAlign = "right";
        tr.append(nameTd, amountTd);
        tbody.appendChild(tr);
    }
    for (const s of toReceive) {
        const tr = document.createElement("tr");
        const nameTd = Object.assign(document.createElement("td"), { textContent: s.from_name });
        nameTd.style.color = "var(--pico-color-green-500)";
        const amountTd = Object.assign(document.createElement("td"), { textContent: `+€${fmt(s.amount)}` });
        amountTd.style.color = "var(--pico-color-green-500)";
        amountTd.style.textAlign = "right";
        tr.append(nameTd, amountTd);
        tbody.appendChild(tr);
    }

    table.appendChild(tbody);
    container.appendChild(table);
}

function renderAdminSettlements(container, settlements, myId) {
    if (settlements.length === 0) {
        container.textContent = "All settled up.";
        return;
    }

    const table = document.createElement("table");
    table.className = "borderless";
    const tbody = document.createElement("tbody");

    for (const s of settlements) {
        const fromIsMe = s.from_user_id === myId;
        const toIsMe = s.to_user_id === myId;

        const fromEl = Object.assign(document.createElement("a"), {
            href: `/users/${s.from_user_id}`, textContent: s.from_name, className: "plain-link"
        });
        const toEl = Object.assign(document.createElement("a"), {
            href: `/users/${s.to_user_id}`, textContent: s.to_name, className: "plain-link"
        });

        const rowColor = fromIsMe ? "var(--pico-color-red-500)" : toIsMe ? "var(--pico-color-green-500)" : null;

        const fromTd = document.createElement("td");
        fromTd.appendChild(fromEl);
        if (rowColor) fromTd.style.color = rowColor;
        const paysTd = Object.assign(document.createElement("td"), { textContent: "pays" });
        paysTd.style.color = "var(--pico-muted-color)";
        const toTd = document.createElement("td");
        toTd.appendChild(toEl);
        if (rowColor) toTd.style.color = rowColor;
        const amountTd = Object.assign(document.createElement("td"), { textContent: `€${fmt(s.amount)}` });
        if (rowColor) amountTd.style.color = rowColor;
        amountTd.style.textAlign = "right";
        const tr = document.createElement("tr");

        tr.append(fromTd, paysTd, toTd, amountTd);
        tbody.appendChild(tr);
    }

    table.appendChild(tbody);
    container.appendChild(table);
}
