import { api, redirectToLogin, fmt } from "./api.js";

const userId = parseInt(window.location.pathname.split("/").pop());

const CHART_COLORS = [
    "#4c78a8", "#f58518", "#e45756", "#72b7b2", "#54a24b",
    "#eeca3b", "#b279a2", "#ff9da6", "#9d755d", "#bab0ac"
];

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

    const userSettlements = settlements.filter(s => s.from_user_id === user.id || s.to_user_id === user.id);
    renderSettlements(userSettlements, user);

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

    // Tab switching — chart rendered lazily on first open
    let chartRendered = false;
    const tabOverview = document.getElementById("tab-overview");
    const tabStats = document.getElementById("tab-stats");
    const panelOverview = document.getElementById("panel-overview");
    const panelStats = document.getElementById("panel-stats");

    tabOverview.addEventListener("click", () => {
        panelOverview.hidden = false;
        panelStats.hidden = true;
        tabOverview.setAttribute("aria-selected", "true");
        tabOverview.className = "";
        tabStats.setAttribute("aria-selected", "false");
        tabStats.className = "outline secondary";
    });

    tabStats.addEventListener("click", () => {
        panelOverview.hidden = true;
        panelStats.hidden = false;
        tabStats.setAttribute("aria-selected", "true");
        tabStats.className = "";
        tabOverview.setAttribute("aria-selected", "false");
        tabOverview.className = "outline secondary";
        if (!chartRendered) {
            renderStats(expenses, user.id);
            chartRendered = true;
        }
    });
};

function renderSettlements(userSettlements, user) {
    const balanceEl = document.getElementById("balance");

    if (userSettlements.length === 0) {
        balanceEl.textContent = "All settled up.";
        return;
    }

    const toPay = userSettlements.filter(s => s.from_user_id === user.id);
    const toReceive = userSettlements.filter(s => s.to_user_id === user.id);

    const totalOwed = toPay.reduce((sum, s) => sum + s.amount, 0);
    const totalReceive = toReceive.reduce((sum, s) => sum + s.amount, 0);
    const net = totalReceive - totalOwed;

    const summary = document.createElement("p");
    summary.style.fontWeight = "bold";
    summary.style.fontSize = "1.1rem";
    if (Math.abs(net) < 0.005) {
        summary.textContent = "All settled up.";
    } else if (net > 0) {
        summary.style.color = "var(--pico-color-green-500)";
        summary.textContent = `You are owed €${fmt(net)} net`;
    } else {
        summary.style.color = "var(--pico-color-red-500)";
        summary.textContent = `You owe €${fmt(-net)} net`;
    }
    balanceEl.appendChild(summary);

    if (toPay.length > 0) {
        const h = document.createElement("h4");
        h.textContent = "You need to pay";
        h.style.marginTop = "1rem";
        balanceEl.appendChild(h);
        balanceEl.appendChild(buildSettlementTable(
            toPay.map(s => ({ label: `→ ${s.to_name}`, amount: s.amount })),
            "var(--pico-color-red-500)"
        ));
    }

    if (toReceive.length > 0) {
        const h = document.createElement("h4");
        h.textContent = "Coming to you";
        h.style.marginTop = "1rem";
        balanceEl.appendChild(h);
        balanceEl.appendChild(buildSettlementTable(
            toReceive.map(s => ({ label: `← ${s.from_name}`, amount: s.amount })),
            "var(--pico-color-green-500)"
        ));
    }
}

function buildSettlementTable(rows, color) {
    const table = document.createElement("table");
    table.className = "borderless";
    table.style.cssText = "width:auto;min-width:16rem;margin:0 auto;";
    const tbody = document.createElement("tbody");
    for (const { label, amount } of rows) {
        const tr = document.createElement("tr");
        const labelTd = document.createElement("td");
        labelTd.textContent = label;
        labelTd.style.color = color;
        const amountTd = document.createElement("td");
        amountTd.textContent = `€${fmt(amount)}`;
        amountTd.style.color = color;
        amountTd.style.textAlign = "right";
        tr.append(labelTd, amountTd);
        tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    return table;
}

function renderStats(expenses, userId) {
    const userExpenses = expenses.filter(e =>
        e.shares.some(s => s.user_id === userId) &&
        (e.category || "").toLowerCase() !== "settlement"
    );

    const monthData = {};
    for (const e of userExpenses) {
        const month = e.date.substring(0, 7);
        if (!monthData[month]) monthData[month] = {};
        monthData[month][e.category] = (monthData[month][e.category] || 0) + e.cost;
    }

    const months = Object.keys(monthData).sort();
    const categories = [...new Set(userExpenses.map(e => e.category))].sort();

    if (months.length === 0) {
        document.getElementById("panel-stats").querySelector("section").appendChild(
            Object.assign(document.createElement("p"), { textContent: "No expenses to display." })
        );
        return;
    }

    const datasets = categories.map((cat, i) => ({
        label: cat,
        data: months.map(m => monthData[m][cat] || 0),
        backgroundColor: CHART_COLORS[i % CHART_COLORS.length],
    }));

    const ctx = document.getElementById("monthly-chart").getContext("2d");
    new Chart(ctx, {
        type: "bar",
        data: { labels: months, datasets },
        options: {
            responsive: true,
            scales: {
                x: { stacked: true },
                y: { stacked: true, beginAtZero: true, ticks: { callback: v => `€${v}` } }
            },
            plugins: {
                legend: { position: "bottom" },
                tooltip: {
                    callbacks: {
                        label: ctx => `${ctx.dataset.label}: €${ctx.parsed.y.toFixed(2)}`
                    }
                }
            }
        }
    });
}
