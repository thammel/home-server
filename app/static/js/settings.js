// Account settings: rename, change own password, or (admin) reset someone's password.
import { api } from "./api.js";
import { boot, showFatal } from "./layout.js";
import { $, confirmButton, el, formatDate, showMessage, toast, mount } from "./ui.js";

const userId = parseInt(window.location.pathname.split("/")[2], 10);

async function start() {
    const { me } = await boot({ allowPasswordChange: true });
    if (!me.is_admin && me.id !== userId) {
        window.location.href = `/users/${me.id}/settings`;
        return;
    }
    const isSelf = me.id === userId;
    const user = isSelf ? me : await api.getUser(userId);
    const forced = isSelf && me.must_change_password;

    // --- name ----------------------------------------------------------------
    const nameInput = el("input", { value: user.name, autocomplete: "username", required: true, maxlength: "50", "aria-label": "Name" });
    const nameMsg = el("p", { hidden: true });
    const nameForm = el("form", {
        onsubmit: async (e) => {
            e.preventDefault();
            try {
                await api.updateUser(userId, { name: nameInput.value.trim() });
                showMessage(nameMsg, "Name updated.", "success");
            } catch (err) {
                showMessage(nameMsg, err.status === 409 ? "That name is taken." : err.message);
            }
        },
    }, el("div", { role: "group" }, nameInput, el("button", { type: "submit" }, "Save")), nameMsg);

    // --- password ------------------------------------------------------------
    const current = isSelf && el("input", {
        type: "password", autocomplete: "current-password", required: true,
        placeholder: forced ? "Current (temporary) password" : "Current password", "aria-label": "Current password",
    });
    const fresh = el("input", { type: "password", autocomplete: "new-password", required: true, minlength: "8", placeholder: "New password (min. 8 characters)", "aria-label": "New password" });
    const confirm = el("input", { type: "password", autocomplete: "new-password", required: true, placeholder: "Repeat new password", "aria-label": "Repeat new password" });
    const pwMsg = el("p", { hidden: true });
    const pwForm = el("form", {
        onsubmit: async (e) => {
            e.preventDefault();
            if (fresh.value.length < 8) return showMessage(pwMsg, "Use at least 8 characters.");
            if (fresh.value !== confirm.value) return showMessage(pwMsg, "Passwords don't match.");
            try {
                await api.updateUser(userId, { password: fresh.value, ...(isSelf ? { current_password: current.value } : {}) });
                pwForm.reset();
                if (forced) {
                    toast("Password set. Welcome!");
                    window.location.href = me.is_admin ? "/admin" : "/";
                    return;
                }
                showMessage(pwMsg, isSelf ? "Password changed. Other devices were logged out." :
                    `Temporary password set. ${user.name} must change it at next login.`, "success");
            } catch (err) {
                showMessage(pwMsg, err.message);
            }
        },
    }, current, fresh, confirm, el("button", { type: "submit" }, isSelf ? "Change password" : "Set temporary password"), pwMsg);

    const bankBox = el("div");
    if (isSelf && !forced && !me.is_admin) renderBank(bankBox).catch(showFatal);

    mount($("#page"),
        !forced && el("a", { href: me.is_admin ? "/admin" : `/users/${userId}`, class: "back" }, "← Back"),
        el("h1", {}, isSelf ? "Your account" : `${user.name}'s account`),
        forced && el("article", { class: "message notice" },
            el("strong", {}, "Choose your own password. "),
            "You're using a temporary password. Set a new one to continue."),
        !forced && el("article", {}, el("h2", {}, "Name"), nameForm),
        el("article", {}, el("h2", {}, isSelf ? "Password" : "Reset password"), pwForm),
        isSelf && !forced && !me.is_admin && bankBox,
    );
    (forced ? current : nameInput).focus();
}

/** Bank connection for importing transactions (ADR 0007). Hidden when the server has no FinTS product ID. */
async function renderBank(box) {
    const status = await api.getBank();
    if (!status.enabled) return mount(box);
    const conn = status.connection;

    const field = (name, attrs) => el("label", {}, attrs["aria-label"],
        el("input", { name, required: true, value: conn?.[name] ?? "", ...attrs }));
    const msg = el("p", { hidden: true });
    const form = el("form", {
        onsubmit: async (e) => {
            e.preventDefault();
            const data = Object.fromEntries(new FormData(form));
            try {
                await api.saveBank({ bank_code: data.bank_code.trim(), server_url: data.server_url.trim(), login_name: data.login_name.trim() });
                toast(conn ? "Bank details saved" : "Bank connected");
                await renderBank(box);
            } catch (err) {
                showMessage(msg, err.message);
            }
        },
    },
    field("bank_code", { "aria-label": "Bank code (BLZ)", inputmode: "numeric", pattern: "\\d{8}", maxlength: "8", autocomplete: "off" }),
    field("server_url", { "aria-label": "FinTS URL", type: "url", placeholder: "https://…", autocomplete: "off" }),
    field("login_name", { "aria-label": "Online banking login", autocomplete: "off" }),
    el("small", { class: "muted" }, "Your PIN is never saved. You type it in each time you sync."),
    el("div", { class: "actions" }, el("button", { type: "submit" }, conn ? "Save" : "Connect")),
    msg);

    const accounts = conn?.accounts.length
        ? el("ul", { class: "plain-list" }, conn.accounts.map(a => el("li", {},
            el("label", { class: "inline-check" },
                el("input", {
                    type: "checkbox", role: "switch", checked: a.enabled,
                    onchange: async (e) => {
                        try {
                            await api.updateBankAccount(a.id, { enabled: e.target.checked });
                        } catch (err) {
                            e.target.checked = !e.target.checked;
                            toast(err.message, "error");
                        }
                    },
                }),
                a.iban))))
        : null;

    mount(box, el("article", {},
        el("h2", {}, "Bank account"),
        conn && el("p", { class: "muted" },
            conn.last_sync_at ? `Last sync ${formatDate(conn.last_sync_at.slice(0, 10))}. ` : "Not synced yet. ",
            el("a", { href: "/bank" }, "Sync and review →")),
        conn?.last_error && el("p", { class: "message error" }, `Last sync failed: ${conn.last_error}`),
        accounts && el("h3", {}, "Accounts to import"),
        accounts,
        form,
        conn && confirmButton("Disconnect bank", "Disconnect and delete imported transactions?", async () => {
            await api.deleteBank();
            toast("Bank disconnected");
            await renderBank(box);
        }, { class: "secondary outline" }),
    ));
}

start().catch(showFatal);
