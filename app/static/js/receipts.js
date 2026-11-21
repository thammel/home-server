// Receipt scanning (ADR 0009): upload a photo, the server reads it in the background,
// then the user reviews the pre-filled expense. Nothing is booked without saving.
import { api } from "./api.js";
import { categoriesByUse } from "./expense-list.js";
import { boot, showFatal } from "./layout.js";
import { createExpenseForm } from "./share-form.js";
import { $, confirmButton, el, formatDate, money, mount, splitEqually, toCents, toast } from "./ui.js";

const POLL_MS = 15000;
const page = $("#page");
let ctx;
let pollTimer;

async function start() {
    const { me, settings } = await boot();
    if (me.is_admin) {
        mount(page, el("article", { class: "message" }, "Admins have no receipts."));
        return;
    }
    const [list, users, categories, expenses] = await Promise.all([
        api.getReceipts(), api.getUsers(), api.getCategories(), api.getExpenses(),
    ]);
    if (!list.enabled) {
        mount(page, el("article", { class: "message" }, "Receipt scanning is not set up on this server."));
        return;
    }
    ctx = {
        me,
        currency: settings.currency,
        people: users.filter(u => u.is_active && !u.is_admin),
        categories: categoriesByUse(expenses, categories),
    };
    const reviewId = Number(new URLSearchParams(window.location.search).get("scan"));
    const toReview = list.scans.find(s => s.id === reviewId && (s.status === "done" || s.status === "failed"));
    if (toReview) renderReview(toReview);
    else renderList(list);
}

function setScanParam(id) {
    const url = new URL(window.location.href);
    if (id) url.searchParams.set("scan", id);
    else url.searchParams.delete("scan");
    history.replaceState(null, "", url);
}

async function reloadList() {
    clearTimeout(pollTimer);
    setScanParam(null);
    renderList(await api.getReceipts());
}

// --- list ------------------------------------------------------------------------

function uploadCard() {
    const msg = el("p", { hidden: true });
    const buttons = [];
    // Android's photo picker offers no camera without `capture`, and with it no library, so both.
    const picker = (label, attrs, cls) => {
        const input = el("input", { type: "file", accept: "image/jpeg,image/png", hidden: true, ...attrs });
        const button = el("button", { type: "button", class: cls, onclick: () => input.click() }, label);
        buttons.push(button);
        input.addEventListener("change", async () => {
            const file = input.files[0];
            input.value = "";
            if (!file) return;
            buttons.forEach(b => { b.disabled = true; });
            button.setAttribute("aria-busy", "true");
            try {
                await api.uploadReceipt(file);
                toast("Receipt uploaded, reading it now");
                await reloadList();
            } catch (err) {
                msg.hidden = false;
                msg.className = "message error";
                msg.textContent = err.message;
            } finally {
                buttons.forEach(b => { b.disabled = false; });
                button.removeAttribute("aria-busy");
            }
        });
        return [button, input];
    };
    return el("article", {},
        el("p", {}, "Take a photo of a receipt. The amount, shop and date are read in the background; you check them before anything is saved."),
        el("div", { class: "actions" },
            picker("Take photo", { capture: "environment" }),
            picker("Choose photo", {}, "secondary outline")),
        msg);
}

function scannerNote(list, waiting) {
    if (!waiting) return null;
    if (list.scanner_reachable === false) {
        const since = list.scanner_last_reachable_at
            ? ` It was last reachable ${new Date(list.scanner_last_reachable_at + "Z").toLocaleString()}.`
            : "";
        return el("article", { class: "message notice" },
            `The scanner is offline. Your receipts wait in the queue and are read once it is back.${since}`);
    }
    return el("p", { class: "muted" }, "Reading takes up to a minute per receipt. This page updates by itself.");
}

function summary(scan) {
    const r = scan.result;
    if (!r) return "Receipt";
    return [r.shop || "Receipt", r.date && formatDate(r.date)].filter(Boolean).join(" · ");
}

function row(scan, side, sub) {
    return el("li", {},
        el("div", { class: "row" },
            el("span", { class: "main" },
                el("span", { class: "title" }, summary(scan)),
                el("span", { class: "sub" }, sub ?? `Uploaded ${formatDate(scan.created_at.slice(0, 10))}`)),
            el("span", { class: "side" }, side)));
}

function renderList(list) {
    const by = (...statuses) => list.scans.filter(s => statuses.includes(s.status));
    const ready = by("done");
    const waiting = by("queued", "processing");
    const failed = by("failed");
    const saved = by("accepted");

    const open = (scan) => () => renderReview(scan);
    const deleteButton = (scan, label = "Delete") => confirmButton(label, "Really delete?", async () => {
        await api.deleteReceipt(scan.id);
        await reloadList();
    }, { class: "link-button" });

    mount(page,
        el("h1", {}, "Receipts"),
        uploadCard(),
        scannerNote(list, waiting.length > 0),
        ready.length > 0 && el("section", {},
            el("h2", {}, `Ready to review (${ready.length})`),
            el("ul", { class: "expense-list" }, ready.map(s => row(s,
                [el("span", { class: "amount" }, money(s.result.total, s.result.currency || undefined)),
                    el("button", { type: "button", class: "link-button", onclick: open(s) }, "Review")])))),
        waiting.length > 0 && el("section", {},
            el("h2", {}, "Being read"),
            el("ul", { class: "expense-list" }, waiting.map(s => row(s,
                el("span", { class: "muted", "aria-busy": s.status === "processing" ? "true" : null },
                    s.status === "processing" ? "Reading" : "Waiting"))))),
        failed.length > 0 && el("section", {},
            el("h2", {}, "Could not be read"),
            el("ul", { class: "expense-list" }, failed.map(s => row(s, [
                el("button", {
                    type: "button", class: "link-button",
                    onclick: async () => { await api.retryReceipt(s.id); await reloadList(); },
                }, "Try again"),
                el("button", { type: "button", class: "link-button", onclick: open(s) }, "Enter by hand"),
                deleteButton(s)], s.error)))),
        saved.length > 0 && el("details", {},
            el("summary", {}, `Saved (${saved.length})`),
            el("ul", { class: "expense-list" }, saved.map(s => row(s, [
                s.expense_id && el("a", { href: `/expenses/${s.expense_id}?next=/receipts` }, "expense"),
                deleteButton(s, "Delete photo")])))),
        list.scans.length === 0 && el("p", { class: "muted empty" }, "No receipts yet."),
    );

    if (waiting.length > 0) {
        pollTimer = setTimeout(() => reloadList().catch(() => {}), POLL_MS);
    }
}

// --- review ----------------------------------------------------------------------

function itemsTable(result) {
    if (!result?.items?.length) return null;
    return el("details", { open: true },
        el("summary", {}, `Items (${result.items.length})`),
        el("table", { class: "receipt-items" },
            el("tbody", {}, result.items.map(i => el("tr", {},
                el("td", {}, i.name),
                el("td", { class: "muted" }, i.quantity !== 1 && i.unit_price != null ? `${i.quantity} × ${money(i.unit_price, result.currency || undefined)}` : ""),
                el("td", { class: "amount" }, money(i.line_total, result.currency || undefined)))))));
}

function prefill(result) {
    const cost = result?.total > 0 ? result.total : 0;
    const ids = ctx.people.map(p => p.id);
    const shares = cost > 0
        ? [{ user_id: ctx.me.id, share: -cost },
            ...splitEqually(toCents(cost), ids.length).map((cents, i) => ({ user_id: ids[i], share: cents / 100 }))]
        : [];
    return {
        cost, description: result?.shop || "", category: "", date: result?.date || undefined,
        comment: "", shares, personal: false,
    };
}

function renderReview(scan) {
    clearTimeout(pollTimer);
    setScanParam(scan.id);
    window.scrollTo(0, 0);
    const result = scan.result;
    const formRoot = el("div");
    const image = el("a", { href: api.receiptImageUrl(scan.id), target: "_blank", rel: "noopener", class: "receipt-photo" },
        el("img", { src: api.receiptImageUrl(scan.id), alt: "Receipt photo" }));
    const notes = [
        !result && el("p", { class: "message notice" }, "This receipt could not be read. Enter the expense by hand."),
        ...(result?.warnings ?? []).map(w => el("p", { class: "message notice" }, `${w}. Check the amount.`)),
        result?.currency && result.currency !== ctx.currency && el("p", { class: "message notice" },
            `The receipt is in ${result.currency}; the expense is saved in ${ctx.currency}. Convert the amount if needed.`),
    ];

    mount(page,
        el("a", { href: "/receipts", class: "back", onclick: (e) => { e.preventDefault(); reloadList(); } }, "← Receipts"),
        el("div", { class: "receipt-review" },
            el("div", {}, image, itemsTable(result)),
            el("article", { class: "form-card" },
                el("h1", {}, "Check and save"),
                notes,
                formRoot,
                el("div", { class: "actions bulk-actions" },
                    confirmButton("Discard receipt", "Really discard?", async () => {
                        await api.deleteReceipt(scan.id);
                        toast("Receipt discarded");
                        await reloadList();
                    }, { class: "secondary outline" })))));

    const expense = prefill(result);
    createExpenseForm(formRoot, {
        people: ctx.people,
        me: ctx.me,
        categories: ctx.categories,
        expense: expense.shares.length ? expense : null,
        submitLabel: "Save expense",
        onSubmit: async (payload) => {
            const saved = await api.addExpense(payload);
            await api.acceptReceipt(scan.id, saved.id);
            toast("Expense saved");
            await reloadList();
        },
        onCancel: () => reloadList(),
    });
}

start().catch(showFatal);
