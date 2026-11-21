// Split a scanned receipt by its lines (ADR 0010). The server derives the shares;
// the totals shown here are a preview using the same rounding.
import { el, mount, money, parseAmount, showMessage, today, toCents } from "./ui.js";

/** Cents per person: each line split equally in its group, rounded once per person by largest remainder. */
export function allocate(lines) {
    const sizes = lines.map(l => l.userIds.length).filter(n => n > 0);
    const gcd = (a, b) => (b ? gcd(b, a % b) : a);
    const denom = sizes.reduce((acc, n) => acc * n / gcd(acc, n), 1);
    const exact = new Map();
    for (const line of lines) {
        if (!line.userIds.length) continue;
        const part = toCents(line.amount) * (denom / line.userIds.length);
        for (const id of line.userIds) exact.set(id, (exact.get(id) ?? 0) + part);
    }
    const cents = new Map([...exact].map(([id, n]) => [id, Math.floor(n / denom)]));
    const total = [...exact.values()].reduce((a, b) => a + b, 0) / denom;
    let left = Math.round(total - [...cents.values()].reduce((a, b) => a + b, 0));
    const byRemainder = [...exact.keys()].sort((a, b) =>
        (cents.get(a) - exact.get(a) / denom) - (cents.get(b) - exact.get(b) / denom) || a - b);
    for (const id of byRemainder) {
        if (left-- <= 0) break;
        cents.set(id, cents.get(id) + 1);
    }
    return cents;
}

/** "Everyone", "Me", a name, or "Anna + Ben" for a group. */
export function groupLabel(userIds, people, meId) {
    const ids = new Set(userIds);
    if (people.length > 1 && people.every(p => ids.has(p.id))) return "Everyone";
    if (ids.size === 1 && ids.has(meId)) return "Me";
    return people.filter(p => ids.has(p.id)).map(p => (p.id === meId ? "Me" : p.name)).join(" + ") || "Nobody";
}

/** Like parseAmount, but discounts may be negative ("-0,50"). */
function parseSigned(text) {
    const trimmed = String(text ?? "").trim();
    const negative = /^[-−]/.test(trimmed);
    const value = parseAmount(negative ? trimmed.slice(1) : trimmed);
    return negative ? -value : value;
}

const sameGroup = (a, b) => a.length === b.length && a.every(id => b.includes(id));

export function createSplitForm(root, { people, me, categories, result, currency, onSubmit }) {
    const everyone = people.map(p => p.id);
    const others = people.filter(p => p.id !== me.id);
    // Tapping the owner chip walks through these; any other group comes from "Choose".
    const cycle = [everyone, [me.id], ...others.map(p => [p.id])];
    const fmt = (amount) => money(amount, currency);

    let lines = (result.items ?? []).map(i => ({
        name: i.name,
        quantity: i.quantity,
        unitPrice: i.unit_price,
        amount: i.line_total,
        userIds: [...everyone],
    }));
    let restIds = [...everyone];

    const total = el("input", { type: "text", inputmode: "decimal", "aria-label": "Receipt total", value: result.total.toFixed(2) });
    const description = el("input", { type: "text", placeholder: "What was it?", "aria-label": "Description", required: true, maxlength: "200", value: result.shop || "" });
    const category = el("input", { type: "text", placeholder: "Category", "aria-label": "Category", list: "split-category-options", required: true, maxlength: "200" });
    const categoryChips = el("div", { class: "chips" }, categories.slice(0, 8).map(c =>
        el("button", { type: "button", class: "chip", onclick: () => { category.value = c; syncChips(); } }, c)));
    const date = el("input", { type: "date", "aria-label": "Date", required: true, value: result.date || today() });
    const privateOwn = el("input", { type: "checkbox", role: "switch" });
    const privateLabel = el("label", { class: "split-private" }, privateOwn, "Keep my own items private (saved as a separate personal expense)");
    const linesBox = el("div", { class: "split-lines" });
    const summary = el("div", { class: "split-summary" });
    const error = el("p", { hidden: true });
    const submit = el("button", { type: "submit" }, "Save expense");

    function syncChips() {
        for (const chip of categoryChips.children) chip.classList.toggle("selected", chip.textContent === category.value.trim());
    }
    category.addEventListener("input", syncChips);

    function nextGroup(current) {
        const at = cycle.findIndex(g => sameGroup(g, current));
        return [...cycle[(at + 1) % cycle.length]];
    }

    function ownerControls(getIds, setIds) {
        const chooser = el("div", { class: "chips split-chooser", hidden: true }, people.map(p => {
            const box = el("input", { type: "checkbox", checked: getIds().includes(p.id) });
            box.addEventListener("change", () => {
                const ids = people.map(q => q.id).filter(id => (id === p.id ? box.checked : getIds().includes(id)));
                if (!ids.length) { box.checked = true; return; }
                setIds(ids);
                chip.textContent = groupLabel(ids, people, me.id);
                updateSummary();
            });
            return el("label", { class: "chip" }, box, p.id === me.id ? "Me" : p.name);
        }));
        const chip = el("button", {
            type: "button", class: "chip selected", title: "Tap to change who this is for",
            onclick: () => { setIds(nextGroup(getIds())); render(); },
        }, groupLabel(getIds(), people, me.id));
        const choose = el("button", {
            type: "button", class: "link-button", onclick: () => { chooser.hidden = !chooser.hidden; },
        }, "Choose…");
        return { owner: el("div", { class: "split-owner" }, chip, choose), chooser };
    }

    function lineRow(line, index) {
        const name = el("input", { type: "text", "aria-label": "Item", maxlength: "200", value: line.name });
        name.addEventListener("input", () => { line.name = name.value; });
        const amount = el("input", { type: "text", inputmode: "decimal", "aria-label": "Amount", class: "split-amount", value: line.amount.toFixed(2) });
        amount.addEventListener("change", () => {
            const value = parseSigned(amount.value);
            if (Number.isNaN(value)) { amount.value = line.amount.toFixed(2); return; }
            line.amount = value;
            line.quantity = 1;
            line.unitPrice = null;
            render();
        });
        const { owner, chooser } = ownerControls(() => line.userIds, (ids) => { line.userIds = ids; });
        const remove = el("button", {
            type: "button", class: "link-button", "aria-label": `Remove ${line.name}`,
            onclick: () => { lines = lines.filter((_, i) => i !== index); render(); },
        }, "Remove");
        const quantity = line.quantity !== 1 && line.unitPrice != null
            ? el("span", { class: "muted" }, `${line.quantity} × ${fmt(line.unitPrice)}`) : null;
        return el("li", {},
            el("div", { class: "split-line" }, name, amount),
            el("div", { class: "split-line-meta" }, owner, quantity, remove),
            chooser);
    }

    function restCents() {
        const totalValue = parseAmount(total.value);
        if (Number.isNaN(totalValue)) return 0;
        return toCents(totalValue) - lines.reduce((sum, l) => sum + toCents(l.amount), 0);
    }

    function linesForSave() {
        const rest = restCents();
        const all = lines.map(l => ({ ...l, name: l.name.trim() || "Item" }));
        if (rest !== 0) all.push({ name: "Rest", quantity: 1, unitPrice: null, amount: rest / 100, userIds: restIds });
        return all.filter(l => toCents(l.amount) !== 0);
    }

    function updateSummary() {
        const all = linesForSave();
        const cents = allocate(all);
        const ownOnly = all.filter(l => sameGroup(l.userIds, [me.id]));
        privateLabel.hidden = !ownOnly.length || ownOnly.length === all.length;
        const rows = people
            .filter(p => cents.get(p.id))
            .map(p => el("li", {},
                el("span", {}, p.id === me.id ? "You" : p.name),
                el("span", { class: "amount" }, fmt(cents.get(p.id) / 100))));
        const restNote = restCents() !== 0
            ? el("p", { class: "muted" }, `The lines differ from the total by ${fmt(restCents() / 100)}; that goes in a "Rest" line.`)
            : null;
        mount(summary, el("ul", { class: "split-people" }, rows), restNote);
    }

    function render() {
        const rest = restCents();
        const restRow = rest !== 0 ? (() => {
            const { owner, chooser } = ownerControls(() => restIds, (ids) => { restIds = ids; });
            return el("li", { class: "split-rest" },
                el("div", { class: "split-line" }, el("span", {}, "Rest"), el("span", { class: "split-amount" }, fmt(rest / 100))),
                el("div", { class: "split-line-meta" }, owner),
                chooser);
        })() : null;
        mount(linesBox,
            el("ul", { class: "split-list" }, lines.map(lineRow), restRow),
            el("button", {
                type: "button", class: "secondary outline",
                onclick: () => { lines.push({ name: "", quantity: 1, unitPrice: null, amount: 0, userIds: [...everyone] }); render(); },
            }, "Add line"));
        updateSummary();
    }
    total.addEventListener("change", render);

    const form = el("form", { class: "expense-form", novalidate: true },
        el("label", {}, "Total paid", total),
        description,
        el("div", { class: "field-group" }, category, categoryChips),
        el("datalist", { id: "split-category-options" }, categories.map(c => el("option", { value: c }))),
        el("p", { class: "muted" }, "Tap who each line is for: everyone, you, or one flatmate. \"Choose…\" picks any group."),
        linesBox,
        summary,
        privateLabel,
        el("details", { class: "more" }, el("summary", {}, "Date"), date),
        error,
        el("div", { class: "actions" }, submit));

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        showMessage(error, "");
        const all = linesForSave();
        try {
            if (Number.isNaN(parseAmount(total.value))) throw new Error("Enter the total paid.");
            if (!description.value.trim()) throw new Error("Add a short description.");
            if (!category.value.trim()) throw new Error("Pick or type a category.");
            if (!date.value) throw new Error("Pick a date.");
            if (!all.length) throw new Error("Add at least one line.");
        } catch (err) {
            showMessage(error, err.message);
            return;
        }
        submit.disabled = true;
        submit.setAttribute("aria-busy", "true");
        try {
            await onSubmit({
                date: date.value,
                description: description.value.trim(),
                category: category.value.trim(),
                private_own: !privateLabel.hidden && privateOwn.checked,
                lines: all.map(l => ({
                    name: l.name, quantity: l.quantity || 1, unit_price: l.unitPrice ?? null,
                    line_total: l.amount, user_ids: l.userIds,
                })),
            });
        } catch (err) {
            showMessage(error, err.message || "Could not save.");
        } finally {
            submit.disabled = false;
            submit.removeAttribute("aria-busy");
        }
    });

    mount(root, form);
    render();
    syncChips();
    return form;
}
