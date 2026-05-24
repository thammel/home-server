import { api, redirectToLogin } from "./api.js";

async function renderUserShareFields() {
    const container = document.getElementById('shares-container');
    const paidBySelect = document.getElementById('paid-by');
    container.innerHTML = 'Loading users...';

    try {
        const [users, me] = await Promise.all([api.getUsers(), api.getMe()]);
        const flatmates = users.filter(u => !u.is_admin);

        container.innerHTML = '';
        paidBySelect.innerHTML = '';

        flatmates.forEach(u => {
            const opt = document.createElement('option');
            opt.value = u.id;
            opt.textContent = u.name;
            if (u.id === me.id) opt.selected = true;
            paidBySelect.appendChild(opt);

            const row = document.createElement('div');
            row.className = 'share-row';
            row.style.display = 'flex';
            row.style.alignItems = 'center';
            row.style.gap = '0.75rem';
            row.style.marginBottom = '6px';

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.id = `check-${u.id}`;
            checkbox.dataset.userId = u.id;
            checkbox.checked = true;

            const label = document.createElement('label');
            label.textContent = u.name;
            label.htmlFor = `check-${u.id}`;
            label.style.margin = '0';

            const input = document.createElement('input');
            input.type = 'number';
            input.id = `share-${u.id}`;
            input.name = `share-${u.id}`;
            input.dataset.userId = u.id;
            input.min = 0;
            input.step = '0.01';
            input.value = 0;
            input.style.width = '8rem';

            checkbox.addEventListener('change', () => {
                input.style.visibility = checkbox.checked ? 'visible' : 'hidden';
                row.style.opacity = checkbox.checked ? '' : '0.4';
                if (!checkbox.checked) input.value = 0;
            });

            row.appendChild(checkbox);
            row.appendChild(label);
            row.appendChild(input);
            container.appendChild(row);
        });

        if (flatmates.length === 0) container.innerHTML = '<em>No users found.</em>';
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
    const shareInputs = document.querySelectorAll('#shares-container input[type="number"]');

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

function splitEqually() {
    const cost = parseFloat(document.getElementById("cost").value);
    if (!cost || isNaN(cost) || cost <= 0) {
        alert("Enter cost first.");
        return;
    }
    const checkedInputs = Array.from(document.querySelectorAll('#shares-container input[type="checkbox"]:checked'))
        .map(cb => document.getElementById(`share-${cb.dataset.userId}`));
    if (checkedInputs.length === 0) {
        alert("Check at least one person to split between.");
        return;
    }
    const n = checkedInputs.length;
    const totalCents = Math.round(cost * 100);
    const baseCents = Math.floor(totalCents / n);
    const extraCount = totalCents - baseCents * n;
    checkedInputs.forEach((input, i) => {
        input.value = ((i < extraCount ? baseCents + 1 : baseCents) / 100).toFixed(2);
    });
}

window.onload = async () => {
    const submitBtn = document.getElementById("add-expense-btn");
    if (submitBtn) submitBtn.disabled = true;
    await renderUserShareFields();
    if (submitBtn) submitBtn.disabled = false;
    window.addExpense = addExpense;
    window.splitEqually = splitEqually;
};
