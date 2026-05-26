import { api, redirectToLogin } from "/static/js/api.js";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];

let state = {
    year: new Date().getFullYear(),
    month: new Date().getMonth(),
    events: [],
    users: [],
    me: null,
    editingEventId: null,
};

// ── Tab wiring ────────────────────────────────────────────────────────────────

const tabSettlements = document.getElementById("tab-settlements");
const tabCalendar    = document.getElementById("tab-calendar");
const panelSettlements = document.getElementById("panel-settlements");
const panelCalendar    = document.getElementById("panel-calendar");

function switchTab(which) {
    const toCalendar = which === "calendar";
    tabSettlements.setAttribute("aria-selected", String(!toCalendar));
    tabCalendar.setAttribute("aria-selected",    String(toCalendar));
    tabSettlements.className = toCalendar ? "outline secondary" : "";
    tabCalendar.className    = toCalendar ? "" : "outline secondary";
    panelSettlements.hidden  = toCalendar;
    panelCalendar.hidden     = !toCalendar;
    if (toCalendar && state.events.length === 0 && state.me === null) {
        initCalendar();
    }
}

tabSettlements.addEventListener("click", () => switchTab("settlements"));
tabCalendar.addEventListener("click",    () => switchTab("calendar"));

// ── Init ─────────────────────────────────────────────────────────────────────

async function initCalendar() {
    try {
        [state.me, state.users, state.events] = await Promise.all([
            api.getMe(),
            api.getUsers(),
            api.calendar.getEvents(),
        ]);
    } catch (e) {
        if (e.status === 401) redirectToLogin();
        return;
    }
    renderGrid();
    bindToolbar();
    bindDialog();
}

// ── Grid rendering ────────────────────────────────────────────────────────────

function renderGrid() {
    const { year, month, events } = state;
    document.getElementById("cal-month-label").textContent = `${MONTHS[month]} ${year}`;

    const grid = document.getElementById("cal-grid");
    grid.innerHTML = "";

    // Header row
    const thead = grid.createTHead();
    const hr = thead.insertRow();
    for (const d of DAYS) {
        const th = document.createElement("th");
        th.textContent = d;
        th.style.cssText = "text-align:center;padding:0.25rem;font-size:0.8rem;";
        hr.appendChild(th);
    }

    const tbody = grid.createTBody();
    const firstDay = new Date(year, month, 1).getDay(); // 0=Sun
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    // offset: Mon=0 … Sun=6
    const offset = (firstDay + 6) % 7;

    let row = tbody.insertRow();
    // empty cells before first day
    for (let i = 0; i < offset; i++) {
        const td = row.insertCell();
        td.style.cssText = "padding:0.25rem;";
    }

    const today = new Date();
    for (let day = 1; day <= daysInMonth; day++) {
        if ((offset + day - 1) % 7 === 0 && day !== 1) {
            row = tbody.insertRow();
        }
        const td = row.insertCell();
        const isToday = today.getFullYear() === year && today.getMonth() === month && today.getDate() === day;
        td.style.cssText = `padding:0.3rem;text-align:center;cursor:pointer;border-radius:0.3rem;vertical-align:top;min-height:2.5rem;${isToday ? "background:var(--pico-primary-background,#1a73e8);color:#fff;" : ""}`;
        td.dataset.day = day;

        const dayLabel = document.createElement("div");
        dayLabel.textContent = day;
        dayLabel.style.cssText = "font-size:0.85rem;font-weight:bold;";
        td.appendChild(dayLabel);

        const dayEvents = events.filter(e => {
            const d = new Date(e.start_dt);
            return d.getFullYear() === year && d.getMonth() === month && d.getDate() === day;
        });
        for (const ev of dayEvents.slice(0, 3)) {
            const dot = document.createElement("div");
            dot.textContent = ev.title;
            dot.style.cssText = "font-size:0.65rem;background:var(--pico-primary,#1a73e8);color:#fff;border-radius:0.2rem;padding:0 0.2rem;margin-top:0.15rem;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;";
            dot.title = ev.title;
            td.appendChild(dot);
        }
        if (dayEvents.length > 3) {
            const more = document.createElement("div");
            more.textContent = `+${dayEvents.length - 3} more`;
            more.style.cssText = "font-size:0.6rem;color:var(--pico-muted-color,#666);";
            td.appendChild(more);
        }

        td.addEventListener("click", () => showDayEvents(day));
    }

    // clear day panel when re-rendering
    document.getElementById("cal-day-events").innerHTML = "";
}

function showDayEvents(day) {
    const { year, month, events, me } = state;
    const panel = document.getElementById("cal-day-events");
    const dayEvents = events.filter(e => {
        const d = new Date(e.start_dt);
        return d.getFullYear() === year && d.getMonth() === month && d.getDate() === day;
    });

    if (dayEvents.length === 0) {
        panel.innerHTML = `<p style="color:var(--pico-muted-color,#666);">No events on ${MONTHS[month]} ${day}.</p>`;
        return;
    }

    panel.innerHTML = `<h4>${MONTHS[month]} ${day}</h4>`;
    for (const ev of dayEvents) {
        const card = document.createElement("article");
        card.style.cssText = "margin-bottom:0.5rem;padding:0.75rem;";

        const start = new Date(ev.start_dt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        const end   = ev.end_dt ? ` – ${new Date(ev.end_dt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : "";
        const canEdit = me.is_admin || ev.creator_id === me.id;

        card.innerHTML = `
            <strong>${escHtml(ev.title)}</strong>
            <span style="float:right;font-size:0.8rem;">${start}${end}</span>
            ${ev.description ? `<p style="margin:0.25rem 0 0;">${escHtml(ev.description)}</p>` : ""}
            ${canEdit ? `<button class="outline secondary" data-edit-id="${ev.id}" style="width:auto;font-size:0.8rem;padding:0.2rem 0.6rem;margin-top:0.5rem;">Edit</button>` : ""}
        `;
        panel.appendChild(card);
    }

    panel.querySelectorAll("[data-edit-id]").forEach(btn => {
        btn.addEventListener("click", () => openEditDialog(parseInt(btn.dataset.editId)));
    });
}

// ── Toolbar ───────────────────────────────────────────────────────────────────

function bindToolbar() {
    document.getElementById("cal-prev").addEventListener("click", () => {
        state.month--;
        if (state.month < 0) { state.month = 11; state.year--; }
        renderGrid();
    });
    document.getElementById("cal-next").addEventListener("click", () => {
        state.month++;
        if (state.month > 11) { state.month = 0; state.year++; }
        renderGrid();
    });
    document.getElementById("cal-new-btn").addEventListener("click", openNewDialog);
    document.getElementById("cal-subscribe-btn").addEventListener("click", async () => {
        try {
            const { url } = await api.calendar.getMyFeedUrl();
            if (navigator.clipboard && navigator.clipboard.writeText) {
                await navigator.clipboard.writeText(url);
                alert(`iCal URL copied to clipboard!\n\nPaste into Google Calendar → "Add by URL" or iOS Calendar → Subscribe to calendar.`);
            } else {
                prompt("Copy this iCal URL and paste into your calendar app:", url);
            }
        } catch (e) {
            alert("Could not get feed URL: " + e.message);
        }
    });
}

// ── Dialog ────────────────────────────────────────────────────────────────────

function bindDialog() {
    const dialog = document.getElementById("cal-event-dialog");
    document.getElementById("cal-dialog-close").addEventListener("click", () => dialog.close());
    document.getElementById("cal-event-form").addEventListener("submit", onFormSubmit);
    document.getElementById("cal-delete-btn").addEventListener("click", onDeleteClick);
}

function openNewDialog() {
    state.editingEventId = null;
    document.getElementById("cal-dialog-title").textContent = "New Event";
    document.getElementById("cal-title").value = "";
    document.getElementById("cal-start-dt").value = "";
    document.getElementById("cal-end-dt").value = "";
    document.getElementById("cal-description").value = "";
    document.getElementById("cal-form-error").textContent = "";
    document.getElementById("cal-delete-btn").style.display = "none";
    renderParticipantCheckboxes([]);
    document.getElementById("cal-event-dialog").showModal();
}

function openEditDialog(eventId) {
    const ev = state.events.find(e => e.id === eventId);
    if (!ev) return;
    state.editingEventId = eventId;
    document.getElementById("cal-dialog-title").textContent = "Edit Event";
    document.getElementById("cal-title").value = ev.title;
    document.getElementById("cal-start-dt").value = toLocalDatetimeInput(ev.start_dt);
    document.getElementById("cal-end-dt").value = ev.end_dt ? toLocalDatetimeInput(ev.end_dt) : "";
    document.getElementById("cal-description").value = ev.description || "";
    document.getElementById("cal-form-error").textContent = "";
    document.getElementById("cal-delete-btn").style.display = "";
    renderParticipantCheckboxes(ev.participants.map(p => p.user_id));
    document.getElementById("cal-event-dialog").showModal();
}

function renderParticipantCheckboxes(selectedIds) {
    const container = document.getElementById("cal-participants-list");
    container.innerHTML = "";
    const nonAdmin = state.users.filter(u => !u.is_admin && u.id !== state.me.id);
    for (const u of nonAdmin) {
        const label = document.createElement("label");
        label.style.cssText = "display:flex;align-items:center;gap:0.5rem;margin-bottom:0.25rem;";
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.value = u.id;
        cb.checked = selectedIds.includes(u.id);
        label.appendChild(cb);
        label.appendChild(document.createTextNode(u.name));
        container.appendChild(label);
    }
}

async function onFormSubmit(e) {
    e.preventDefault();
    const errEl = document.getElementById("cal-form-error");
    errEl.textContent = "";

    const title = document.getElementById("cal-title").value.trim();
    const startRaw = document.getElementById("cal-start-dt").value;
    const endRaw   = document.getElementById("cal-end-dt").value;
    const desc  = document.getElementById("cal-description").value.trim();
    const participantIds = [...document.querySelectorAll("#cal-participants-list input:checked")].map(cb => parseInt(cb.value));

    if (!title || !startRaw) { errEl.textContent = "Title and start time required."; return; }

    const payload = {
        title,
        description: desc || null,
        start_dt: new Date(startRaw).toISOString(),
        end_dt: endRaw ? new Date(endRaw).toISOString() : null,
        participant_ids: participantIds,
    };

    try {
        if (state.editingEventId) {
            await api.calendar.updateEvent(state.editingEventId, payload);
        } else {
            await api.calendar.createEvent(payload);
        }
        state.events = await api.calendar.getEvents();
        document.getElementById("cal-event-dialog").close();
        renderGrid();
    } catch (err) {
        errEl.textContent = err.message || "Save failed.";
    }
}

async function onDeleteClick() {
    if (!state.editingEventId) return;
    if (!confirm("Delete this event?")) return;
    try {
        await api.calendar.deleteEvent(state.editingEventId);
        state.events = await api.calendar.getEvents();
        document.getElementById("cal-event-dialog").close();
        renderGrid();
    } catch (err) {
        document.getElementById("cal-form-error").textContent = err.message || "Delete failed.";
    }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function escHtml(str) {
    return str.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

function toLocalDatetimeInput(isoStr) {
    const d = new Date(isoStr);
    // datetime-local format: "YYYY-MM-DDTHH:MM"
    const pad = n => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
