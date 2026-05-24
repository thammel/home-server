const BASE_URL = "";

async function request(path, options = {}) {
    const res = await fetch(path, {
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {})
        },
        credentials: "same-origin",
        ...options
    });

    if (!res.ok) {
        const err = new Error(res.statusText);
        err.status = res.status;
        if (res.status === 401) {
            err.message = "Unauthorized";
        }
        const text = await res.text();
        err.message = text || err.message;
        throw err;
    }

    return res.status !== 204 ? res.json() : null;
}

export function fmt(n) {
    return (+n).toFixed(2);
}

export function redirectToLogin() {
    const next = window.location.pathname + window.location.search;
    window.location.href = `/?next=${encodeURIComponent(next)}`;
}

export const api = {
    getUsers() {
        return request("/api/users/");
    },

    getUser(userId) {
        return request(`/api/users/${userId}`);
    },

    getMe() {
        return request("/api/users/me");
    },

    getExpenses() {
        return request("/api/expenses/");
    },

    getExpense(expenseId) {
        return request(`/api/expenses/${expenseId}/`);
    },

    getBalances() {
        return request("/api/balances/");
    },

    getSettlements(mode = "simplified") {
        return request(`/api/balances/settlements/?mode=${mode}`);
    },

    getSettings() {
        return request("/api/settings/");
    },

    updateSettings(payload) {
        return request("/api/settings/", { method: "PATCH", body: JSON.stringify(payload) });
    },

    addExpense(expense) {
        return request("/api/expenses/", {
            method: "POST",
            body: JSON.stringify(expense)
        });
    },

    updateExpense(expenseId, payload) {
        return request(`/api/expenses/${expenseId}`, {
            method: "PATCH",
            body: JSON.stringify(payload)
        });
    },

    deleteExpense(expenseId) {
        return request(`/api/expenses/${expenseId}`, {
            method: "DELETE"
        });
    },

    createUser(payload) {
        return request("/api/users/", {
            method: "POST",
            body: JSON.stringify(payload)
        });
    },

    updateUser(userId, payload) {
        return request(`/api/users/${userId}`, {
            method: "PATCH",
            body: JSON.stringify(payload)
        });
    },

    deleteUser(userId) {
        return request(`/api/users/${userId}`, {
            method: "DELETE"
        });
    },

    login(payload) {
        return request("/api/auth/login", {
            method: "POST",
            body: JSON.stringify(payload)
        });
    },

    logout() {
        return request("/api/auth/logout", {
            method: "POST"
        });
    }
};
