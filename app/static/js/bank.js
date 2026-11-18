// Bank import: sync with the PIN, then go through new transactions one by one (ADR 0007).
import { api } from "./api.js";
import { categoriesByUse } from "./expense-list.js";
import { boot, showFatal } from "./layout.js";
import { createExpenseForm } from "./share-form.js";
import { $, el, formatDate, money, mount, showMessage, splitEqually, toCents, toast } from "./ui.js";

const page = $("#page");
const syncBox = el("div");
const reviewBox = el("div");
const doneBox = el("div");
let ctx;

async function start() {
    const { me } = await boot();
    if (me.is_admin) {
        mount(page, el("article", { class: "message" }, "Admins have no bank import."));
        return;
    }
    const [status, users, categories, expenses] = await Promise.all([
        api.getBank(), api.getUsers(), api.getCategories(), api.getExpenses(),
    ]);
    if (!status.enabled) {
        mount(page, el("article", { class: "message" }, "Bank import is not set up on this server."));
        return;
    }
    if (!status.connection) {
        mount(page, el("h1", {}, "Bank"), el("article", { class: "message notice" },
            "No bank connected yet. ", el("a", { href: `/users/${me.id}/settings` }, "Connect one in your account settings")));
        return;
    }
    ctx = {
        me, status,
        people: users.filter(u => u.is_active && !u.is_admin),
        categories: categoriesByUse(expenses, categories),
    };
    mount(page, el("h1", {}, "Bank"), syncBox, reviewBox, doneBox);
    renderSyncForm();
    await loadReview();
}

// --- sync ----------------------------------------------------------------------

function renderSyncForm() {
    const pin = el("input", {
        type: "password", autocomplete: "off", required: true, placeholder: "Online banking PIN", "aria-label": "PIN",
    });
    const since = el("input", { type: "date", "aria-label": "Fetch from", value: ctx.status.default_since ?? "" });
    const msg = el("p", { hidden: true });
    const submit = el("button", { type: "submit" }, "Sync");
    const form = el("form", {
        onsubmit: async (e) => {
            e.preventDefault();
            if (!pin.value) return showMessage(msg, "Enter your PIN.");
            submit.disabled = true;
            submit.setAttribute("aria-busy", "true");
            try {
                const result = await api.startBankSync({ pin: pin.value, since: since.value || null });
                pin.value = "";
                await handleSync(result);
            } catch (err) {
                pin.value = "";
                showMessage(msg, err.message);
            } finally {
                submit.disabled = false;
                submit.removeAttribute("aria-busy");
            }
        },
    },
    el("div", { class: "grid" },
        el("label", {}, "PIN", pin),
        el("label", {}, "Fetch from", since)),
    el("small", { class: "muted" }, "The PIN is used for this sync only and never saved."),
    el("div", { class: "actions" }, submit),
    msg);

    const conn = ctx.status.connection;
    mount(syncBox, el("article", {},
        el("h2", {}, "Sync"),
        el("p", { class: "muted" }, conn.last_sync_at ? `Last sync ${formatDate(conn.last_sync_at.slice(0, 10))}.` : "Not synced yet."),
        form));
}

async function handleSync(result) {
    if (result.status === "done") {
        toast(`${result.new} new, ${result.known} already known`);
        ctx.status = await api.getBank();
        renderSyncForm();
        await loadReview();
        return;
    }
    const tan = el("input", { type: "text", inputmode: "numeric", autocomplete: "one-time-code", placeholder: "TAN", "aria-label": "TAN" });
    const msg = el("p", { hidden: true });
    const proceed = el("button", {
        type: "button",
        onclick: async () => {
            proceed.disabled = true;
            proceed.setAttribute("aria-busy", "true");
            try {
                await handleSync(await api.continueBankSync(result.sync_id, { tan: result.decoupled ? "" : tan.value }));
            } catch (err) {
                showMessage(msg, err.message);
                proceed.disabled = false;
                proceed.removeAttribute("aria-busy");
                if (err.status === 404) renderSyncForm();
            }
        },
    }, result.decoupled ? "I approved it" : "Send TAN");
    const cancel = el("button", {
        type: "button", class: "secondary outline",
        onclick: async () => {
            await api.cancelBankSync(result.sync_id).catch(() => {});
            renderSyncForm();
        },
    }, "Cancel");
    mount(syncBox, el("article", { class: "message notice" },
        el("h2", {}, "Approval needed"),
        el("p", {}, result.challenge),
        result.decoupled ? el("p", { class: "muted" }, "Approve it in your banking app, then continue. This expires after 5 minutes.") : tan,
        el("div", { class: "actions" }, proceed, cancel),
        msg));
}

// --- review --------------------------------------------------------------------

async function loadReview() {
    const all = await api.getBankTransactions();
    const fresh = all.filter(t => t.status === "new");
    renderReview(fresh, 0);
    renderDone(all.filter(t => t.status !== "new"));
}

function describe(t) {
    return t.counterparty || t.purpose.slice(0, 60) || "Bank transaction";
}

function renderReview(items, index) {
    if (items.length === 0) {
        mount(reviewBox, el("article", {}, el("h2", {}, "Review"), el("p", { class: "muted empty" }, "Nothing to review.")));
        return;
    }
    index = Math.min(Math.max(index, 0), items.length - 1);
    const t = items[index];
    const next = () => {
        items.splice(index, 1);
        renderReview(items, index);
    };
    const settle = async (payload) => {
        await api.updateBankTransaction(t.id, payload);
        next();
        await refreshDone();
    };
    const body = el("div");

    const personal = () => {
        const category = el("input", { type: "text", list: "bank-categories", placeholder: "Category", "aria-label": "Category", required: true });
        const chips = el("div", { class: "chips" }, ctx.categories.slice(0, 8).map(c =>
            el("button", { type: "button", class: "chip", onclick: () => { category.value = c; } }, c)));
        const msg = el("p", { hidden: true });
        mount(body, el("form", {
            onsubmit: async (e) => {
                e.preventDefault();
                if (!category.value.trim()) return showMessage(msg, "Pick or type a category.");
                const cost = -t.amount;
                try {
                    const expense = await api.addExpense({
                        date: t.booking_date, description: describe(t), category: category.value.trim(),
                        comment: t.purpose.slice(0, 1000), cost,
                        shares: [{ user_id: ctx.me.id, share: -cost }, { user_id: ctx.me.id, share: cost }],
                    });
                    await settle({ expense_id: expense.id });
                    toast("Saved as personal expense");
                } catch (err) {
                    showMessage(msg, err.message);
                }
            },
        }, category, chips,
        el("datalist", { id: "bank-categories" }, ctx.categories.map(c => el("option", { value: c }))),
        el("div", { class: "actions" }, el("button", { type: "submit" }, "Save personal expense")), msg));
        category.focus();
    };

    const split = () => {
        const cost = -t.amount;
        const ids = ctx.people.map(p => p.id);
        const shares = [{ user_id: ctx.me.id, share: -cost },
            ...splitEqually(toCents(cost), ids.length).map((cents, i) => ({ user_id: ids[i], share: cents / 100 }))];
        createExpenseForm(body, {
            people: ctx.people, me: ctx.me, categories: ctx.categories,
            expense: { cost, description: describe(t), category: "", date: t.booking_date, comment: t.purpose.slice(0, 1000), shares, personal: false },
            submitLabel: "Save expense",
            onSubmit: async (payload) => {
                const expense = await api.addExpense(payload);
                await settle({ expense_id: expense.id });
                toast("Expense saved");
            },
            onCancel: () => mount(body),
        });
    };

    const incoming = t.amount > 0;
    mount(reviewBox, el("article", {},
        el("div", { class: "section-head" },
            el("h2", {}, "Review"),
            el("span", { class: "muted" }, `${index + 1} of ${items.length}`)),
        el("p", { class: "hero-amount" }, money(t.amount, t.currency)),
        el("p", {}, el("strong", {}, describe(t)), " · ", formatDate(t.booking_date)),
        t.purpose && el("p", { class: "muted" }, t.purpose),
        t.possible_duplicate_expense_id && el("p", { class: "message notice" },
            "Possibly already recorded: ",
            el("a", { href: `/expenses/${t.possible_duplicate_expense_id}?next=/bank` }, "open expense"),
            ". Ignore this line if it is the same payment."),
        el("div", { class: "actions" },
            !incoming && el("button", { type: "button", onclick: personal }, "Personal"),
            !incoming && el("button", { type: "button", class: "secondary", onclick: split }, "Split"),
            el("button", { type: "button", class: "secondary outline", onclick: () => settle({ status: "ignored" }).catch(err => toast(err.message, "error")) }, "Ignore"),
            el("button", { type: "button", class: "secondary outline", disabled: index === 0, onclick: () => renderReview(items, index - 1) }, "Back"),
            el("button", { type: "button", class: "secondary outline", disabled: index === items.length - 1, onclick: () => renderReview(items, index + 1) }, "Skip for now")),
        body,
    ));
}

// --- handled ---------------------------------------------------------------------

async function refreshDone() {
    renderDone((await api.getBankTransactions()).filter(t => t.status !== "new"));
}

function renderDone(rows) {
    if (rows.length === 0) return mount(doneBox);
    const list = (status, title) => {
        const items = rows.filter(r => r.status === status).sort((a, b) => b.booking_date.localeCompare(a.booking_date));
        return el("details", {},
            el("summary", {}, `${title} (${items.length})`),
            el("ul", { class: "expense-list" }, items.map(t => el("li", {},
                el("div", { class: "row" },
                    el("span", { class: "main" },
                        el("span", { class: "title" }, describe(t)),
                        el("span", { class: "sub" }, formatDate(t.booking_date),
                            t.expense_id ? [" · ", el("a", { href: `/expenses/${t.expense_id}?next=/bank` }, "expense")] : null)),
                    el("span", { class: "side" },
                        el("span", { class: "amount" }, money(t.amount, t.currency)),
                        el("button", {
                            type: "button", class: "link-button",
                            onclick: async () => {
                                await api.updateBankTransaction(t.id, { status: "new" });
                                await loadReview();
                            },
                        }, "Review again")))))));
    };
    mount(doneBox, el("section", {}, list("ignored", "Ignored"), list("booked", "Recorded")));
}

start().catch(showFatal);
