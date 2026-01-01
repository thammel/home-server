import { api } from "./api.js";

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
            input.max = 100;
            input.step = 0.01;
            input.value = 0;

            row.appendChild(label);
            row.appendChild(input);
            container.appendChild(row);
        });

        if (users.length === 0) container.innerHTML = '<em>No users found.</em>';
    } catch (err) {
        container.innerHTML = '<em>Failed to load users.</em>';
        console.error(err);
    }
}

function collectSharesAsPercentages() {
    const inputs = document.querySelectorAll('#shares-container input[type="number"]');
    const shares = [];
    inputs.forEach(i => {
        const pct = parseFloat(i.value) || 0;
        shares.push({ user_id: parseInt(i.dataset.userId, 10), percent: pct });
    });
    return shares;
}

async function addExpense() {
    const description = document.getElementById("description").value;
    const amount = parseFloat(document.getElementById("amount").value);
    const paidById = parseInt(document.getElementById("paid-by").value);

    const sharesPercentages = collectSharesAsPercentages();
    const totalPercentage = sharesPercentages.reduce((sum, s) => sum + s.percent, 0);

    if (totalPercentage !== 100) {
        alert("Total share percentages must equal 100%.");
        return;
    }

    const expense = {
        description: description,
        amount: amount,
        paid_by_id: paidById,
        shares: sharesPercentages.map(s => ({
            user_id: s.user_id,
            share_amount: (s.percent / 100) * amount
        }))
    };

    await api.addExpense(expense);
    
    window.location.href = "/";
}

// initialize on load
renderUserShareFields();

window.addExpense = addExpense;