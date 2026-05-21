import { api, redirectToLogin } from "./api.js";

async function renderUserShareFields() {
    const container = document.getElementById('shares-container');
    container.innerHTML = 'Loading users...';

    try {
        const users = await api.getUsers();

        container.innerHTML = '';
        users.forEach(u => {
            const row = document.createElement('div');
            row.className = 'share-row';
            row.style.marginBottom = '6px';

            const label = document.createElement('label');
            label.textContent = u.name;
            label.style.marginRight = '8px';
            label.htmlFor = `share-${u.id}`;

            const input = document.createElement('input');
            input.type = 'number';
            input.id = `share-${u.id}`;
            input.name = `share-${u.id}`;
            input.dataset.userId = u.id;
            input.min = 0;
            input.value = 0;

            row.appendChild(label);
            row.appendChild(input);
            container.appendChild(row);
        });

        if (users.length === 0) container.innerHTML = '<em>No users found.</em>';
    } catch (err) {
        if (err.status === 401) {
            redirectToLogin();
            return;
        }
        if (err.status === 403) {
            container.innerHTML = '<em>Not authorized.</em>';
            return;
        }
        container.innerHTML = '<em>Failed to load users.</em>';
        console.error(err);
    }
}

async function addExpense() {
    const date = document.getElementById("date").value;
    const description = document.getElementById("description").value;
    const category = document.getElementById("category").value;
    const cost = parseFloat(document.getElementById("cost").value);
    const currency = document.getElementById("currency").value;
    const comment = document.getElementById("comment").value;
    const paidById = parseInt(document.getElementById("paid-by").value);
    const shareInputs = document.querySelectorAll('#shares-container input');

    const shares = Array.from(shareInputs).map(s => {
    const id = parseInt(s.dataset.userId);
    const value = parseFloat(s.value) || 0;
    return {
        user_id: id,
        share: id === paidById ? -value : value
    };
});

    if (!cost || isNaN(cost) || cost <= 0) {
        alert("Cost must be a positive number.");
        return;
    }
    const positiveShares = shares.filter(s => s.share > 0);
    if (positiveShares.length === 0) {
        alert("At least one user must have a non-zero share.");
        return;
    }
    const totalPositive = positiveShares.reduce((sum, s) => sum + s.share, 0);
    if (Math.abs(totalPositive - cost) > 0.01) {
        alert(`Shares total (${totalPositive.toFixed(2)}) must equal cost (${cost.toFixed(2)}).`);
        return;
    }

    const expense = {
        date: date,
        description: description,
        category: category,
        cost: cost,
        currency: currency,
        comment: comment,
        shares: shares,
    };

    try {
        await api.addExpense(expense);
    } catch (err) {
        if (err.status === 401) {
            redirectToLogin();
            return;
        }
        throw err;
    }

    window.location.href = "/";
}

window.onload = async () => {
    const submitBtn = document.getElementById("add-expense-btn");
    if (submitBtn) submitBtn.disabled = true;
    await renderUserShareFields();
    if (submitBtn) submitBtn.disabled = false;
    window.addExpense = addExpense;
};
