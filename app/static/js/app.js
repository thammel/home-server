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

    const visible = isAdmin ? settlements : settlements.filter(s => s.from_user_id === myId || s.to_user_id === myId);

    if (visible.length === 0) {
        container.textContent = "All settled up.";
        return;
    }

    const table = document.createElement("table");
    table.className = "borderless";
    const tbody = document.createElement("tbody");

    for (const s of visible) {
        const fromIsMe = s.from_user_id === myId;
        const toIsMe = s.to_user_id === myId;

        const fromEl = (fromIsMe || isAdmin)
            ? Object.assign(document.createElement("a"), { href: `/users/${s.from_user_id}`, textContent: s.from_name, className: "plain-link" })
            : Object.assign(document.createElement("span"), { textContent: s.from_name });

        const toEl = (toIsMe || isAdmin)
            ? Object.assign(document.createElement("a"), { href: `/users/${s.to_user_id}`, textContent: s.to_name, className: "plain-link" })
            : Object.assign(document.createElement("span"), { textContent: s.to_name });

        const tr = document.createElement("tr");
        if (fromIsMe) tr.style.color = "var(--pico-color-red-500)";
        if (toIsMe)   tr.style.color = "var(--pico-color-green-500)";

        const fromTd = document.createElement("td");
        fromTd.appendChild(fromEl);

        const paysTd = document.createElement("td");
        paysTd.textContent = "pays";
        paysTd.style.color = "var(--pico-muted-color)";

        const toTd = document.createElement("td");
        toTd.appendChild(toEl);

        const amountTd = document.createElement("td");
        amountTd.textContent = `€${fmt(s.amount)}`;
        amountTd.style.textAlign = "right";

        tr.append(fromTd, paysTd, toTd, amountTd);
        tbody.appendChild(tr);
    }

    table.appendChild(tbody);
    container.appendChild(table);
}
