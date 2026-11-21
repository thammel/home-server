// Single source for all API calls.

async function request(path, options = {}) {
    const res = await fetch(path, {
        credentials: "same-origin",
        ...options,
        headers: {
            // FormData sets its own multipart boundary.
            ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
            ...(options.headers || {}),
        },
    });

    if (!res.ok) {
        const err = new Error(await errorMessage(res));
        err.status = res.status;
        throw err;
    }
    return res.status !== 204 ? res.json() : null;
}

async function errorMessage(res) {
    const text = await res.text();
    try {
        const { detail } = JSON.parse(text);
        if (typeof detail === "string") return detail;
        // Pydantic validation errors: [{loc, msg}, ...]
        if (Array.isArray(detail)) {
            return detail.map(d => `${d.loc?.slice(1).join(".") || "input"}: ${d.msg}`).join("; ");
        }
    } catch { /* not JSON */ }
    return text || res.statusText;
}

const json = (method, body) => ({ method, body: JSON.stringify(body) });

export const api = {
    login: (payload) => request("/api/auth/login", json("POST", payload)),
    logout: () => request("/api/auth/logout", { method: "POST" }),

    getMe: () => request("/api/users/me"),
    getUsers: () => request("/api/users/"),
    getUser: (userId) => request(`/api/users/${userId}`),
    createUser: (payload) => request("/api/users/", json("POST", payload)),
    updateUser: (userId, payload) => request(`/api/users/${userId}`, json("PATCH", payload)),
    deleteUser: (userId) => request(`/api/users/${userId}`, { method: "DELETE" }),

    getExpenses: ({ userId } = {}) =>
        request(userId != null ? `/api/expenses/?user_id=${userId}` : "/api/expenses/"),
    getExpense: (expenseId) => request(`/api/expenses/${expenseId}`),
    getCategories: () => request("/api/expenses/categories"),
    addExpense: (expense) => request("/api/expenses/", json("POST", expense)),
    updateExpense: (expenseId, payload) => request(`/api/expenses/${expenseId}`, json("PATCH", payload)),
    deleteExpense: (expenseId) => request(`/api/expenses/${expenseId}`, { method: "DELETE" }),

    getBalances: () => request("/api/balances/"),
    // mode omitted -> server uses the app setting
    getSettlements: () => request("/api/balances/settlements/"),

    getSettings: () => request("/api/settings/"),
    updateSettings: (payload) => request("/api/settings/", json("PATCH", payload)),

    getBank: () => request("/api/bank/"),
    saveBank: (payload) => request("/api/bank/", json("PUT", payload)),
    deleteBank: () => request("/api/bank/", { method: "DELETE" }),
    updateBankAccount: (accountId, payload) => request(`/api/bank/accounts/${accountId}`, json("PATCH", payload)),
    startBankSync: (payload) => request("/api/bank/sync", json("POST", payload)),
    continueBankSync: (syncId, payload) => request(`/api/bank/sync/${encodeURIComponent(syncId)}/continue`, json("POST", payload)),
    cancelBankSync: (syncId) => request(`/api/bank/sync/${encodeURIComponent(syncId)}`, { method: "DELETE" }),
    getBankTransactions: (status) => request("/api/bank/transactions" + (status ? `?status=${status}` : "")),
    updateBankTransaction: (txId, payload) => request(`/api/bank/transactions/${txId}`, json("PATCH", payload)),
    ignoreNewBankTransactions: () => request("/api/bank/transactions/ignore-new", { method: "POST" }),
    undoLastBankSync: () => request("/api/bank/last-sync", { method: "DELETE" }),

    getReceipts: () => request("/api/receipts/"),
    uploadReceipt: (file) => {
        const body = new FormData();
        body.append("file", file);
        return request("/api/receipts/", { method: "POST", body });
    },
    acceptReceipt: (scanId, expenseId) => request(`/api/receipts/${scanId}/accept`, json("POST", { expense_id: expenseId })),
    splitReceipt: (scanId, body) => request(`/api/receipts/${scanId}/split`, json("POST", body)),
    retryReceipt: (scanId) => request(`/api/receipts/${scanId}/retry`, { method: "POST" }),
    deleteReceipt: (scanId) => request(`/api/receipts/${scanId}`, { method: "DELETE" }),
    receiptImageUrl: (scanId) => `/api/receipts/${scanId}/image`,
};

export function redirectToLogin() {
    const next = window.location.pathname + window.location.search;
    window.location.href = `/?next=${encodeURIComponent(next)}`;
}
