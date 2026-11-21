// Quick add: amount, what, category, then save — sensible defaults for the rest.
import { api } from "./api.js";
import { boot, showFatal } from "./layout.js";
import { createExpenseForm } from "./share-form.js";
import { categoriesByUse } from "./expense-list.js";
import { $, el, safeNext, mount } from "./ui.js";

async function start() {
    const { me } = await boot();
    const [users, categories, expenses] = await Promise.all([api.getUsers(), api.getCategories(), api.getExpenses()]);
    const people = users.filter(u => u.is_active && !u.is_admin);
    const next = safeNext(new URLSearchParams(window.location.search).get("next"));
    const page = $("#page");

    if (people.length === 0) {
        mount(page, el("article", { class: "message" },
            "No flatmates yet. ", me.is_admin ? el("a", { href: "/admin" }, "Add users in Admin") : "Ask the admin to add users."));
        return;
    }

    const formRoot = el("div");
    const scanBox = el("div");
    mount(page, scanBox, el("article", { class: "form-card" }, el("h1", {}, "Add expense"), formRoot));
    if (!me.is_admin) showScanEntry(scanBox);
    createExpenseForm(formRoot, {
        people,
        me,
        categories: categoriesByUse(expenses, categories),
        submitLabel: "Add expense",
        onSubmit: async (payload) => {
            await api.addExpense(payload);
            window.location.href = next;
        },
        onCancel: () => { window.location.href = next; },
    });
}

/** Link to receipt scanning, with the number of scans waiting for review (ADR 0009). */
async function showScanEntry(box) {
    let list;
    try {
        list = await api.getReceipts();
    } catch {
        return;
    }
    if (!list.enabled) return;
    const ready = list.scans.filter(s => s.status === "done").length;
    mount(box, el("article", { class: "scan-entry" },
        el("span", {}, "Have a receipt?",
            ready ? el("span", { class: "badge accent", title: `${ready} ready to review` }, `${ready} ready`) : null),
        el("a", { href: "/receipts", role: "button", class: "secondary outline" }, ready ? "Review receipts" : "Scan receipt")));
}

start().catch(showFatal);
