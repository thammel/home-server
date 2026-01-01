const BASE_URL = "";

async function request(path, options = {}) {
    const res = await fetch(path, {
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {})
        },
        ...options
    });

    if (!res.ok) {
        const text = await res.text();
        throw new Error(text || res.statusText);
    }

    return res.status !== 204 ? res.json() : null;
}

export const api = {
    getUsers() {
        return request("/api/users/");
    },

    getExpenses() {
        return request("/api/expenses/");
    },

    getBalances() {
        return request("/api/balances/");
    },

    addExpense(expense) {
        return request("/api/expenses/", {
            method: "POST",
            body: JSON.stringify(expense)
        });
    }
};
