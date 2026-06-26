import { api, redirectToLogin } from "./api.js";

let currentUserId = null;

window.onload = () => {
    init();
};

async function init() {
    let me;
    try {
        me = await api.getMe();
    } catch (err) {
        redirectToLogin();
        return;
    }

    if (!me.is_admin) {
        window.location.href = "/";
        return;
    }

    currentUserId = me.id;
    await loadUsers();
    await loadSettings();

    const addUserForm = document.getElementById("add-user-form");
    addUserForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const errorEl = document.getElementById("add-user-error");
        errorEl.textContent = "";
        const name = document.getElementById("new-name").value.trim();
        const password = document.getElementById("new-password").value;
        const submitBtn = addUserForm.querySelector("button[type=submit]");
        submitBtn.disabled = true;
        try {
            await api.createUser({ name, password });
            document.getElementById("new-name").value = "";
            document.getElementById("new-password").value = "";
            await loadUsers();
        } catch (err) {
            errorEl.textContent = err.message || "Failed to create user.";
        } finally {
            submitBtn.disabled = false;
        }
    });
}

async function loadSettings() {
    const settings = await api.getSettings();
    applyModeButtons(settings.settlement_mode);

    document.getElementById("mode-simplified").addEventListener("click", async () => {
        await api.updateSettings({ settlement_mode: "simplified" });
        applyModeButtons("simplified");
    });
    document.getElementById("mode-full").addEventListener("click", async () => {
        await api.updateSettings({ settlement_mode: "full" });
        applyModeButtons("full");
    });
}

function applyModeButtons(mode) {
    document.getElementById("mode-simplified").className = mode === "simplified" ? "" : "secondary";
    document.getElementById("mode-full").className = mode === "full" ? "" : "secondary";
}

async function loadUsers() {
    const users = await api.getUsers();
    renderUsers(users);
}

function renderUsers(users) {
    const tbody = document.getElementById("users-body");
    tbody.innerHTML = "";
    users.forEach(user => {
        const tr = document.createElement("tr");

        const nameTd = document.createElement("td");
        nameTd.textContent = user.name;

        const adminTd = document.createElement("td");
        adminTd.textContent = user.is_admin ? "Yes" : "No";

        const actionsTd = document.createElement("td");

        const toggleBtn = document.createElement("button");
        toggleBtn.type = "button";
        toggleBtn.textContent = user.is_admin ? "Revoke Admin" : "Make Admin";
        toggleBtn.addEventListener("click", () => toggleAdmin(user.id, user.is_admin));

        const deleteBtn = document.createElement("button");
        deleteBtn.type = "button";
        deleteBtn.textContent = "Delete";
        deleteBtn.style.marginLeft = "0.5rem";
        deleteBtn.disabled = user.id === currentUserId;
        deleteBtn.addEventListener("click", () => deleteUser(user.id, user.name));

        actionsTd.appendChild(toggleBtn);
        actionsTd.appendChild(deleteBtn);

        tr.appendChild(nameTd);
        tr.appendChild(adminTd);
        tr.appendChild(actionsTd);
        tbody.appendChild(tr);
    });
}

async function toggleAdmin(userId, currentIsAdmin) {
    try {
        await api.updateUser(userId, { is_admin: !currentIsAdmin });
        await loadUsers();
    } catch (err) {
        alert(err.message || "Failed to update user.");
    }
}

async function deleteUser(userId, name) {
    if (!confirm(`Delete user "${name}"? This cannot be undone.`)) return;
    try {
        await api.deleteUser(userId);
        await loadUsers();
    } catch (err) {
        alert(err.message || "Failed to delete user.");
    }
}
