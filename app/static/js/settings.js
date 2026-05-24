import { api, redirectToLogin } from "./api.js";

const userId = parseInt(window.location.pathname.split("/")[2]);

window.onload = async () => {
    let me;
    try {
        me = await api.getMe();
    } catch (err) {
        if (err.status === 401) { redirectToLogin(); return; }
        throw err;
    }

    if (!me.is_admin && me.id !== userId) {
        window.location.href = `/users/${me.id}`;
        return;
    }

    const user = (me.id === userId) ? me : await api.getUser(userId);

    document.getElementById("back-link").href = `/users/${userId}`;
    document.getElementById("new-name").value = user.name;

    const nameMsg = document.getElementById("name-msg");
    const passwordMsg = document.getElementById("password-msg");

    document.getElementById("name-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        nameMsg.textContent = "";
        nameMsg.className = "";
        const name = document.getElementById("new-name").value.trim();
        try {
            await api.updateUser(userId, { name });
            nameMsg.textContent = "Name updated.";
        } catch (err) {
            nameMsg.className = "error";
            nameMsg.textContent = err.status === 409 ? "Name already taken." : "Failed to update name.";
        }
    });

    document.getElementById("password-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        passwordMsg.textContent = "";
        passwordMsg.className = "";
        const password = document.getElementById("new-password").value;
        const confirm = document.getElementById("confirm-password").value;
        if (password !== confirm) {
            passwordMsg.className = "error";
            passwordMsg.textContent = "Passwords do not match.";
            return;
        }
        try {
            await api.updateUser(userId, { password });
            passwordMsg.textContent = "Password updated.";
            document.getElementById("password-form").reset();
        } catch {
            passwordMsg.className = "error";
            passwordMsg.textContent = "Failed to update password.";
        }
    });
};
