import {api} from "./api.js";

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

    const expense = {
         date: date,
         description: description,
         category: category,
         cost: cost,
         currency: currency,
         comment: comment,
         shares: shares,
     };

    await api.addExpense(expense);

    window.location.href = "/";
}

// initialize on load
renderUserShareFields();

window.addExpense = addExpense;
