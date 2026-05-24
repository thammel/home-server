import { api, redirectToLogin, fmt } from "./api.js";

const expenseId = parseInt(window.location.pathname.split("/").pop());

window.onload = async () => {
    const params = new URLSearchParams(window.location.search);
    const next = params.get("next") || "/";
    const backLink = document.getElementById("back-link");
    if (backLink) backLink.href = next;

    let expense, users, me;
    try {
        [expense, users, me] = await Promise.all([
            api.getExpense(expenseId),
            api.getUsers(),
            api.getMe()
        ]);
    } catch (err) {
        if (err.status === 401) { redirectToLogin(); return; }
        if (err.status === 403) {
            document.getElementById("expense-title").textContent = "Not authorized";
            return;
        }
        throw err;
    }

    renderDetails(expense, users);

    const canEdit = me.is_admin || expense.shares.some(s => s.user_id === me.id && s.share < 0);
    if (canEdit) {
        const actions = document.getElementById("actions");
        actions.hidden = false;
        actions.classList.add("expense-actions");
        actions.style.marginTop = "1rem";

        setupEditForm(expense, users, me);
        setupDeleteButton(next);
    }
};

function renderDetails(expense, users) {
    const nameOf = Object.fromEntries(users.map(u => [u.id, u.name]));

    document.getElementById("expense-title").textContent = expense.description;

    const meta = document.getElementById("expense-meta");
    const fields = [
        ["Date", new Date(expense.date).toLocaleDateString()],
        ["Category", expense.category],
        ["Cost", `€${fmt(expense.cost)} ${expense.currency}`],
    ];
    if (expense.comment) fields.push(["Comment", expense.comment]);
    meta.innerHTML = fields.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");

    const netByUser = {};
    expense.shares.forEach(s => {
        netByUser[s.user_id] = (netByUser[s.user_id] ?? 0) + s.share;
    });

    const tbody = document.querySelector("#shares-table tbody");
    tbody.innerHTML = "";
    Object.entries(netByUser)
        .sort(([, a], [, b]) => a - b)
        .forEach(([userId, net]) => {
            const tr = document.createElement("tr");
            const nameTd = document.createElement("td");
            nameTd.textContent = nameOf[userId] ?? `User ${userId}`;
            const balanceTd = document.createElement("td");
            if (net < 0) {
                balanceTd.style.color = "var(--pico-color-green-500)";
                balanceTd.textContent = `+€${fmt(-net)}`;
            } else {
                balanceTd.style.color = "var(--pico-color-red-500)";
                balanceTd.textContent = `-€${fmt(net)}`;
            }
            tr.append(nameTd, balanceTd);
            tbody.appendChild(tr);
        });
}

function setupDeleteButton(redirectPath) {
    document.getElementById("delete-btn").addEventListener("click", async () => {
        if (!confirm("Delete this expense? This cannot be undone.")) return;
        try {
            await api.deleteExpense(expenseId);
            window.location.href = redirectPath;
        } catch (err) {
            if (err.status === 401) { redirectToLogin(); return; }
            alert(`Failed to delete: ${err.message}`);
        }
    });
}

function setupEditForm(expense, users, me) {
    const flatmates = users.filter(u => !u.is_admin);

    // Determine existing payer and consumptions from shares
    const netByUser = {};
    expense.shares.forEach(s => {
        netByUser[s.user_id] = (netByUser[s.user_id] ?? 0) + s.share;
    });
    const payerEntry = Object.entries(netByUser).find(([, net]) => net < 0);
    const paidById = payerEntry ? parseInt(payerEntry[0]) : (flatmates[0]?.id ?? null);

    const consumptions = {};
    expense.shares.forEach(s => {
        if (s.share > 0) consumptions[s.user_id] = (consumptions[s.user_id] ?? 0) + s.share;
    });

    // Pre-fill scalar fields
    document.getElementById("edit-date").value = expense.date.split("T")[0];
    document.getElementById("edit-description").value = expense.description;
    document.getElementById("edit-category").value = expense.category || "";
    document.getElementById("edit-cost").value = expense.cost;
    document.getElementById("edit-currency").value = expense.currency || "EUR";
    document.getElementById("edit-comment").value = expense.comment || "";

    // Populate paid-by select
    const paidBySelect = document.getElementById("edit-paid-by");
    paidBySelect.innerHTML = "";
    flatmates.forEach(u => {
        const opt = document.createElement("option");
        opt.value = u.id;
        opt.textContent = u.name;
        if (u.id === paidById) opt.selected = true;
        paidBySelect.appendChild(opt);
    });

    // Populate per-user share rows
    const container = document.getElementById("edit-shares-container");
    container.innerHTML = "";
    flatmates.forEach(u => {
        const consumption = consumptions[u.id] ?? 0;

        const row = document.createElement("div");
        row.className = "share-row";
        row.style.cssText = "display:flex;align-items:center;gap:0.75rem;margin-bottom:6px";

        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.id = `edit-check-${u.id}`;
        checkbox.dataset.userId = u.id;
        checkbox.checked = consumption > 0;

        const label = document.createElement("label");
        label.textContent = u.name;
        label.htmlFor = `edit-check-${u.id}`;
        label.style.margin = "0";

        const input = document.createElement("input");
        input.type = "number";
        input.id = `edit-share-${u.id}`;
        input.dataset.userId = u.id;
        input.min = 0;
        input.step = "0.01";
        input.value = consumption > 0 ? consumption.toFixed(2) : "0";
        input.style.width = "8rem";
        if (!checkbox.checked) input.style.visibility = "hidden";

        checkbox.addEventListener("change", () => {
            input.style.visibility = checkbox.checked ? "visible" : "hidden";
            row.style.opacity = checkbox.checked ? "" : "0.4";
            if (!checkbox.checked) input.value = "0";
        });

        row.append(checkbox, label, input);
        container.appendChild(row);
    });

    // Edit/cancel toggle
    document.getElementById("edit-btn").addEventListener("click", () => {
        document.getElementById("edit-form").hidden = false;
        document.getElementById("edit-btn").hidden = true;
    });
    document.getElementById("edit-cancel-btn").addEventListener("click", () => {
        document.getElementById("edit-form").hidden = true;
        document.getElementById("edit-btn").hidden = false;
        document.getElementById("edit-error").hidden = true;
    });

    document.getElementById("edit-save-btn").addEventListener("click", saveEdit);
    document.getElementById("edit-split-btn").addEventListener("click", editSplitEqually);
}

function editSplitEqually() {
    const cost = parseFloat(document.getElementById("edit-cost").value);
    if (!cost || isNaN(cost) || cost <= 0) { alert("Enter cost first."); return; }

    const checkedInputs = Array.from(
        document.querySelectorAll('#edit-shares-container input[type="checkbox"]:checked')
    ).map(cb => document.getElementById(`edit-share-${cb.dataset.userId}`));

    if (checkedInputs.length === 0) { alert("Check at least one person to split between."); return; }

    const n = checkedInputs.length;
    const totalCents = Math.round(cost * 100);
    const baseCents = Math.floor(totalCents / n);
    const extraCount = totalCents - baseCents * n;
    checkedInputs.forEach((input, i) => {
        input.value = ((i < extraCount ? baseCents + 1 : baseCents) / 100).toFixed(2);
    });
}

async function saveEdit() {
    const date = document.getElementById("edit-date").value;
    const description = document.getElementById("edit-description").value;
    const category = document.getElementById("edit-category").value;
    const cost = parseFloat(document.getElementById("edit-cost").value);
    const currency = document.getElementById("edit-currency").value;
    const comment = document.getElementById("edit-comment").value;
    const paidById = parseInt(document.getElementById("edit-paid-by").value);
    const shareInputs = document.querySelectorAll('#edit-shares-container input[type="number"]');
    const errorEl = document.getElementById("edit-error");

    errorEl.hidden = true;

    if (!cost || isNaN(cost) || cost <= 0) {
        errorEl.textContent = "Cost must be a positive number.";
        errorEl.hidden = false;
        return;
    }

    const shares = [];
    shareInputs.forEach(s => {
        const id = parseInt(s.dataset.userId);
        const value = parseFloat(s.value) || 0;
        if (id === paidById) {
            shares.push({ user_id: id, share: -cost });
            if (value > 0) shares.push({ user_id: id, share: value });
        } else {
            if (value > 0) shares.push({ user_id: id, share: value });
        }
    });

    const positiveShares = shares.filter(s => s.share > 0);
    if (positiveShares.length === 0) {
        errorEl.textContent = "At least one user must have a non-zero share.";
        errorEl.hidden = false;
        return;
    }
    const totalPositive = positiveShares.reduce((sum, s) => sum + s.share, 0);
    if (Math.abs(totalPositive - cost) > 0.01) {
        errorEl.textContent = `Shares total (${totalPositive.toFixed(2)}) must equal cost (${cost.toFixed(2)}).`;
        errorEl.hidden = false;
        return;
    }

    const saveBtn = document.getElementById("edit-save-btn");
    saveBtn.disabled = true;
    try {
        await api.updateExpense(expenseId, { date, description, category, cost, currency, comment, shares });
        window.location.reload();
    } catch (err) {
        if (err.status === 401) { redirectToLogin(); return; }
        errorEl.textContent = err.message || "Failed to save.";
        errorEl.hidden = false;
    } finally {
        saveBtn.disabled = false;
    }
}
