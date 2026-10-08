/**
 * EXAMEN Ambient Intelligence & Peace of Mind Hub Frontend Logic
 * Supports Alexa+ Echo Show (ext-apps) and Desktop/Mobile Web Browsers
 */

document.addEventListener("DOMContentLoaded", () => {
  // State
  let actionsData = [];
  let routinesData = [];
  let socialData = [];
  let topicsData = [];
  let isSSEConnected = false;

  // DOM Elements - Telemetry
  const elStatus = document.getElementById("telemetry-status");
  const elProvider = document.getElementById("telemetry-provider");
  const elModel = document.getElementById("telemetry-model");
  const btnRefresh = document.getElementById("btn-refresh");

  // DOM Elements - Badges
  const badgeActions = document.getElementById("badge-actions-count");
  const badgeRoutines = document.getElementById("badge-routines-count");
  const badgeSocial = document.getElementById("badge-social-count");
  const badgeBriefings = document.getElementById("badge-briefings-count");

  // DOM Elements - Hero
  const heroTitle = document.getElementById("hero-action-title");
  const heroQuote = document.getElementById("hero-action-quote");
  const heroTime = document.getElementById("hero-action-time");
  const heroElapsed = document.getElementById("hero-action-elapsed");
  const heroConf = document.getElementById("hero-action-conf");

  // DOM Elements - Grids, Timelines & Lists
  const actionsGrid = document.getElementById("actions-grid");
  const actionsTimeline = document.getElementById("actions-timeline");
  const btnViewTimeline = document.getElementById("btn-view-timeline");
  const btnViewGrid = document.getElementById("btn-view-grid");
  const routinesList = document.getElementById("routines-list");
  const socialGrid = document.getElementById("social-grid");
  const briefingsList = document.getElementById("briefings-list");

  // DOM Elements - Routine Stats
  const statRoutinesTotal = document.getElementById("stat-routines-total");
  const statRoutinesCompleted = document.getElementById("stat-routines-completed");
  const statRoutinesPending = document.getElementById("stat-routines-pending");

  // DOM Elements - Add Routine Form
  const btnToggleAddTask = document.getElementById("btn-toggle-add-task");
  const addTaskDrawer = document.getElementById("add-task-drawer");
  const formAddTask = document.getElementById("form-add-task");
  const btnCancelTask = document.getElementById("btn-cancel-task");

  // DOM Elements - Edit Routine Form
  const editTaskDrawer = document.getElementById("edit-task-drawer");
  const formEditTask = document.getElementById("form-edit-task");
  const btnCancelEditTask = document.getElementById("btn-cancel-edit-task");
  const editTaskId = document.getElementById("edit-task-id");
  const editTaskTitle = document.getElementById("edit-task-title");
  const editTaskDomain = document.getElementById("edit-task-domain");
  const editTaskTime = document.getElementById("edit-task-time");
  const editTaskRecurrence = document.getElementById("edit-task-recurrence");

  // DOM Elements - Search
  const filterActions = document.getElementById("filter-actions");
  const filterSocial = document.getElementById("filter-social");
  const filterTopics = document.getElementById("filter-topics");

  // DOM Elements - Simulator
  const simInput = document.getElementById("sim-input");
  const btnRunSim = document.getElementById("btn-run-simulation");
  const simSpinner = document.getElementById("sim-spinner");
  const simOutputBox = document.getElementById("sim-output-box");
  const simLatency = document.getElementById("sim-latency");
  const simRawJson = document.getElementById("sim-raw-json");
  const presetButtons = document.querySelectorAll(".btn-preset");

  // -------------------------------------------------------------------------
  // Navigation & Tabs
  // -------------------------------------------------------------------------
  const navTabs = document.querySelectorAll(".nav-tab");
  const tabPanes = document.querySelectorAll(".tab-pane");

  navTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const targetPaneId = tab.dataset.tab;

      navTabs.forEach((t) => t.classList.remove("active"));
      tabPanes.forEach((p) => p.classList.remove("active"));

      tab.classList.add("active");
      const targetPane = document.getElementById(targetPaneId);
      if (targetPane) targetPane.classList.add("active");
    });
  });

  // -------------------------------------------------------------------------
  // View Switcher (Chronological Timeline vs Cards Grid)
  // -------------------------------------------------------------------------
  btnViewTimeline?.addEventListener("click", () => {
    btnViewTimeline.classList.add("active");
    btnViewGrid?.classList.remove("active");
    actionsTimeline?.classList.remove("hidden");
    actionsGrid?.classList.add("hidden");
  });

  btnViewGrid?.addEventListener("click", () => {
    btnViewGrid.classList.add("active");
    btnViewTimeline?.classList.remove("active");
    actionsGrid?.classList.remove("hidden");
    actionsTimeline?.classList.add("hidden");
  });

  // -------------------------------------------------------------------------
  // Toast Notifications
  // -------------------------------------------------------------------------
  function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;

    let icon = "ℹ️";
    if (type === "success") icon = "✓";
    if (type === "error") icon = "⚠️";

    toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(100%)";
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  }

  // -------------------------------------------------------------------------
  // Fetch Functions
  // -------------------------------------------------------------------------

  async function fetchStatus() {
    try {
      const res = await fetch("/api/status");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      if (!isSSEConnected) {
        elStatus.textContent = "Engine Active";
      }
      elProvider.textContent = (data.config.gatekeeper_provider || "Bedrock").toUpperCase();
      
      const modelName = data.config.gatekeeper_model || "Nemotron";
      elModel.textContent = modelName.includes(".") ? modelName.split(".")[1] : modelName;

      badgeActions.textContent = data.stats.total_actions || 0;
      badgeRoutines.textContent = data.stats.planned_tasks_total || 0;
      badgeSocial.textContent = data.stats.total_contacts || 0;
      badgeBriefings.textContent = data.stats.total_topics || 0;

      statRoutinesTotal.textContent = data.stats.planned_tasks_total || 0;
      statRoutinesCompleted.textContent = data.stats.planned_tasks_completed || 0;
      statRoutinesPending.textContent = data.stats.planned_tasks_pending || 0;
    } catch (err) {
      console.warn("Failed to fetch /api/status:", err);
      elStatus.textContent = "Offline / Syncing";
    }
  }

  async function fetchActions() {
    try {
      const res = await fetch("/api/actions?limit=50");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      actionsData = data.actions || [];
      renderActions(actionsData);
    } catch (err) {
      console.error("Error fetching actions:", err);
      if (actionsGrid) actionsGrid.innerHTML = `<div class="empty-state">Failed to load actions. Verify server status.</div>`;
      if (actionsTimeline) actionsTimeline.innerHTML = `<div class="empty-state">Failed to load action timeline.</div>`;
    }
  }

  async function fetchRoutines() {
    try {
      const res = await fetch("/api/routines");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      routinesData = data.tasks || [];
      renderRoutines(routinesData);
    } catch (err) {
      console.error("Error fetching routines:", err);
      if (routinesList) routinesList.innerHTML = `<div class="empty-state">Failed to load scheduled routines.</div>`;
    }
  }

  async function fetchSocial() {
    try {
      const res = await fetch("/api/contacts");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      socialData = data.contacts || [];
      renderSocial(socialData);
    } catch (err) {
      console.error("Error fetching social contacts:", err);
      if (socialGrid) socialGrid.innerHTML = `<div class="empty-state">Failed to load social contacts.</div>`;
    }
  }

  async function fetchTopics() {
    try {
      const res = await fetch("/api/topics?limit=20");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      topicsData = data.topics || [];
      renderTopics(topicsData);
    } catch (err) {
      console.error("Error fetching topics:", err);
      if (briefingsList) briefingsList.innerHTML = `<div class="empty-state">Failed to load briefings.</div>`;
    }
  }

  async function refreshAll() {
    await Promise.all([
      fetchStatus(),
      fetchActions(),
      fetchRoutines(),
      fetchSocial(),
      fetchTopics(),
    ]);
  }

  // -------------------------------------------------------------------------
  // Render Functions
  // -------------------------------------------------------------------------

  function renderActions(actions) {
    if (!actions || actions.length === 0) {
      heroTitle.textContent = "No verified actions yet";
      heroQuote.textContent = "Actions like unplugging the iron, locking the door, or taking medications will appear here.";
      heroTime.textContent = "-";
      heroElapsed.textContent = "-";
      heroConf.textContent = "-";
      if (actionsGrid) actionsGrid.innerHTML = `<div class="empty-state">No verified actions detected. Try the Ambient Simulator tab to run a sample speech stream!</div>`;
      if (actionsTimeline) actionsTimeline.innerHTML = `<div class="empty-state">No verified actions recorded yet in the timeline. Run the Ambient Simulator to create one!</div>`;
      return;
    }

    // Hero: Top action is the most recent
    const latest = actions[0];
    heroTitle.textContent = latest.action_type.replace(/_/g, " ").toUpperCase();
    heroQuote.textContent = `"${latest.raw_statement || 'Action confirmed by user.'}"`;
    heroTime.textContent = latest.timestamp.includes("T") ? latest.timestamp.split("T")[1]?.slice(0, 8) : latest.timestamp;
    heroElapsed.textContent = latest.elapsed_time_human;
    heroConf.textContent = `${Math.round(latest.confidence * 100)}%`;

    // Render Cards Grid
    if (actionsGrid) {
      actionsGrid.innerHTML = actions.map((a) => {
        let badgeClass = "badge-routine";
        if (a.domain === "safety") badgeClass = "badge-safety";
        if (a.domain === "work_task") badgeClass = "badge-work";

        const timeFormatted = a.timestamp.includes("T") ? a.timestamp.split("T")[1]?.slice(0, 5) : a.timestamp;

        return `
          <div class="action-card">
            <div class="card-top-row">
              <span class="card-badge ${badgeClass}">${escapeHtml(a.domain)}</span>
              <span class="card-elapsed">${escapeHtml(a.elapsed_time_human || '')}</span>
            </div>
            <div class="card-title">${escapeHtml(a.action_type.replace(/_/g, " "))}</div>
            <div class="card-quote">"${escapeHtml(a.raw_statement || '')}"</div>
            <div class="card-footer">
              <span>Detected at ${escapeHtml(timeFormatted)}</span>
              <span class="conf-pill">✓ ${Math.round(a.confidence * 100)}% conf</span>
            </div>
          </div>
        `;
      }).join("");
    }

    // Render Chronological Timeline
    renderTimeline(actions);
  }

  function renderTimeline(actions) {
    if (!actionsTimeline) return;
    if (!actions || actions.length === 0) {
      actionsTimeline.innerHTML = `<div class="empty-state">No verified actions recorded yet in the timeline.</div>`;
      return;
    }

    // Sort descending chronologically
    const sorted = [...actions].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

    actionsTimeline.innerHTML = sorted.map((a) => {
      let pinClass = "pin-routine";
      let pinIcon = "📋";
      let badgeClass = "badge-routine";

      if (a.domain === "safety") {
        pinClass = "pin-safety";
        pinIcon = "🛡️";
        badgeClass = "badge-safety";
      } else if (a.domain === "work_task") {
        pinClass = "pin-work";
        pinIcon = "💼";
        badgeClass = "badge-work";
      }

      const timeFormatted = a.timestamp.includes("T")
        ? a.timestamp.split("T")[1]?.slice(0, 8)
        : a.timestamp;

      const dateFormatted = a.timestamp.includes("T")
        ? a.timestamp.split("T")[0]
        : "";

      const taskLinkHtml = a.matched_task_id
        ? `<div class="timeline-task-link"><span>✓ Matched Routine #${escapeHtml(a.matched_task_id)}</span></div>`
        : "";

      return `
        <div class="timeline-item">
          <div class="timeline-pin ${pinClass}" title="${escapeHtml(a.domain)}">${pinIcon}</div>
          <div class="timeline-card">
            <div class="timeline-header">
              <span class="card-badge ${badgeClass}">${escapeHtml(a.domain)}</span>
              <div class="timeline-header-right">
                <span class="timeline-time-badge">⏱️ ${escapeHtml(timeFormatted)}</span>
                <span class="card-elapsed">${escapeHtml(a.elapsed_time_human || '')}</span>
              </div>
            </div>
            <div class="timeline-body">
              <div class="timeline-title">${escapeHtml(a.action_type.replace(/_/g, " ").toUpperCase())}</div>
              <div class="timeline-quote">"${escapeHtml(a.raw_statement || 'Action confirmed by audio stream.')}"</div>
              ${taskLinkHtml}
            </div>
            <div class="timeline-footer">
              <span>Date: ${escapeHtml(dateFormatted)}</span>
              <span class="conf-pill">✓ ${Math.round(a.confidence * 100)}% verified</span>
            </div>
          </div>
        </div>
      `;
    }).join("");
  }

  function renderRoutines(routines) {
    if (!routinesList) return;
    if (!routines || routines.length === 0) {
      routinesList.innerHTML = `<div class="empty-state">No routines scheduled. Click '+ Schedule Routine' above to add one.</div>`;
      return;
    }

    routinesList.innerHTML = routines.map((r) => {
      const isCompleted = r.status === "completed";
      const statusClass = isCompleted ? "status-completed" : "status-pending";
      const icon = isCompleted ? "✓" : "○";
      const badgeText = isCompleted ? "Audio Verified" : "Watching Stream";

      return `
        <div class="routine-item ${statusClass}" data-id="${r.id}">
          <div class="routine-left">
            <button class="routine-toggle-btn" data-action="toggle" data-id="${r.id}" title="${isCompleted ? 'Mark Pending' : 'Mark Completed'}">
              ${icon}
            </button>
            <div>
              <div class="routine-title-text">${escapeHtml(r.title)}</div>
              <div class="routine-meta">
                <span>Category: <strong>${escapeHtml(r.domain)}</strong></span>
                ${r.scheduled_time ? `<span>Target: <strong>${escapeHtml(r.scheduled_time)}</strong></span>` : ""}
                <span>Recurrence: <strong>${escapeHtml(r.recurrence)}</strong></span>
                ${isCompleted && r.completed_at ? `<span>Completed at: <strong class="highlight-text">${escapeHtml(r.completed_at)}</strong></span>` : ""}
              </div>
            </div>
          </div>
          <div class="routine-right">
            <span class="routine-badge-tag">${badgeText}</span>
            <div class="routine-actions">
              <button class="btn-action-icon btn-action-edit" data-action="edit" data-id="${r.id}" title="Edit routine">✏️</button>
              <button class="btn-action-icon btn-action-delete" data-action="delete" data-id="${r.id}" title="Delete routine">🗑️</button>
            </div>
          </div>
        </div>
      `;
    }).join("");
  }

  function renderSocial(contacts) {
    if (!socialGrid) return;
    if (!contacts || contacts.length === 0) {
      socialGrid.innerHTML = `<div class="empty-state">No contacts recorded yet. Mention someone and your promises in ambient conversation!</div>`;
      return;
    }

    socialGrid.innerHTML = contacts.map((c) => {
      const topicsHtml = (c.key_topics || [])
        .map((t) => `<span class="topic-tag">#${escapeHtml(t)}</span>`)
        .join("");

      const commitmentsHtml = (c.commitments && c.commitments.length > 0)
        ? `
          <div class="social-commitments-box">
            <div class="commitments-header">📌 Bilateral Commitments (${c.commitments.length})</div>
            <ul class="commitments-list">
              ${c.commitments.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
            </ul>
          </div>
        `
        : "";

      return `
        <div class="social-card">
          <div class="card-title">${escapeHtml(c.name)}</div>
          <div class="card-role">${escapeHtml(c.company_or_role || 'Independent / Contact')}</div>
          ${topicsHtml ? `<div class="social-topics-tags">${topicsHtml}</div>` : ""}
          ${commitmentsHtml}
          <div class="card-footer">
            <span>First met: ${c.timestamp ? c.timestamp.split("T")[0] : "-"}</span>
            ${c.contact_info ? `<span>${escapeHtml(c.contact_info)}</span>` : ""}
          </div>
        </div>
      `;
    }).join("");
  }

  function renderTopics(topics) {
    if (!briefingsList) return;
    if (!topics || topics.length === 0) {
      briefingsList.innerHTML = `<div class="empty-state">No technical dossiers generated yet. EXAMEN synthesizes them automatically during technical meetings.</div>`;
      return;
    }

    briefingsList.innerHTML = topics.map((t) => {
      const summaryItems = (t.executive_summary || [])
        .map((s) => `<li>${escapeHtml(s)}</li>`)
        .join("");

      const sourcesItems = (t.web_sources || [])
        .map((s) => `<a href="${escapeHtml(s)}" target="_blank" rel="noopener noreferrer" class="source-link">🔗 ${escapeHtml(s.replace(/https?:\/\/(www\.)?/, '').slice(0, 30))}...</a>`)
        .join("");

      const actionsItems = (t.action_items && t.action_items.length > 0)
        ? `
          <div class="social-commitments-box" style="margin-top: 1rem;">
            <div class="commitments-header">📋 Meeting Action Items</div>
            <ul class="commitments-list">
              ${t.action_items.map((act) => `<li>${escapeHtml(act)}</li>`).join("")}
            </ul>
          </div>
        `
        : "";

      const synthesisBox = t.explanatory_synthesis
        ? `
          <div class="briefing-explanatory-box">
            <div class="explanatory-header">
              <span class="explanatory-icon">💡</span>
              <span class="explanatory-title">Contextual Explanatory Synthesis</span>
              <span class="explanatory-badge">${escapeHtml(t.context_type || 'tech_stack').toUpperCase()}</span>
            </div>
            <div class="explanatory-content">${escapeHtml(t.explanatory_synthesis)}</div>
          </div>
        `
        : "";

      return `
        <div class="briefing-card">
          <div class="card-top-row">
            <span class="card-badge badge-work">${escapeHtml(t.context_type || 'tech_stack')}</span>
            <span class="card-elapsed">${t.created_at ? t.created_at.split("T")[0] : "-"}</span>
          </div>
          <h3 class="card-title">${escapeHtml(t.topic_title)}</h3>
          <ul class="briefing-summary-bullets">
            ${summaryItems}
          </ul>
          ${synthesisBox}
          ${sourcesItems ? `<div class="sources-row"><span>Autonomously Consulted Sources:</span> ${sourcesItems}</div>` : ""}
          ${actionsItems}
        </div>
      `;
    }).join("");
  }

  // -------------------------------------------------------------------------
  // Search & Filtering Handlers
  // -------------------------------------------------------------------------

  filterActions?.addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase().trim();
    if (!q) {
      renderActions(actionsData);
      return;
    }
    const filtered = actionsData.filter(
      (a) =>
        a.action_type.toLowerCase().includes(q) ||
        (a.raw_statement && a.raw_statement.toLowerCase().includes(q)) ||
        a.domain.toLowerCase().includes(q)
    );
    renderActions(filtered);
  });

  filterSocial?.addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase().trim();
    if (!q) {
      renderSocial(socialData);
      return;
    }
    const filtered = socialData.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        (c.company_or_role && c.company_or_role.toLowerCase().includes(q)) ||
        (c.key_topics && c.key_topics.some((t) => t.toLowerCase().includes(q)))
    );
    renderSocial(filtered);
  });

  filterTopics?.addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase().trim();
    if (!q) {
      renderTopics(topicsData);
      return;
    }
    const filtered = topicsData.filter((t) =>
      t.topic_title.toLowerCase().includes(q)
    );
    renderTopics(filtered);
  });

  // -------------------------------------------------------------------------
  // Routine CRUD Handlers (Add, Edit, Delete, Toggle)
  // -------------------------------------------------------------------------

  // Toggle Add Task Form
  btnToggleAddTask?.addEventListener("click", () => {
    addTaskDrawer.classList.toggle("hidden");
    editTaskDrawer?.classList.add("hidden");
  });

  btnCancelTask?.addEventListener("click", () => {
    addTaskDrawer.classList.add("hidden");
  });

  // Submit Add Task Form
  formAddTask?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const title = document.getElementById("task-title").value.trim();
    const domain = document.getElementById("task-domain").value;
    const time = document.getElementById("task-time").value;
    const recurrence = document.getElementById("task-recurrence").value;

    if (!title) return;

    try {
      const res = await fetch("/api/routines", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          domain,
          scheduled_time: time,
          recurrence,
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showToast(`Scheduled routine: "${title}"`, "success");
      formAddTask.reset();
      addTaskDrawer.classList.add("hidden");

      await refreshAll();
    } catch (err) {
      console.error("Failed to add routine:", err);
      showToast("Error creating routine. Check console.", "error");
    }
  });

  // Cancel Edit Task Form
  btnCancelEditTask?.addEventListener("click", () => {
    editTaskDrawer.classList.add("hidden");
  });

  // Submit Edit Task Form
  formEditTask?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const taskId = editTaskId.value;
    const title = editTaskTitle.value.trim();
    const domain = editTaskDomain.value;
    const time = editTaskTime.value;
    const recurrence = editTaskRecurrence.value;

    if (!taskId || !title) return;

    try {
      const res = await fetch(`/api/routines/${encodeURIComponent(taskId)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          domain,
          scheduled_time: time,
          recurrence,
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showToast(`Updated routine: "${title}"`, "success");
      editTaskDrawer.classList.add("hidden");
      await refreshAll();
    } catch (err) {
      console.error("Failed to update routine:", err);
      showToast("Error updating routine. Check console.", "error");
    }
  });

  // Event Delegation for Routines List (Toggle, Edit, Delete)
  routinesList?.addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const action = btn.dataset.action;
    const taskId = btn.dataset.id;
    if (!taskId) return;

    if (action === "toggle") {
      try {
        const res = await fetch(`/api/routines/${encodeURIComponent(taskId)}/toggle`, {
          method: "POST",
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        showToast(data.message || "Routine status updated", "success");
        await refreshAll();
      } catch (err) {
        console.error("Failed to toggle routine status:", err);
        showToast("Error toggling routine status", "error");
      }
    } else if (action === "delete") {
      if (!confirm("Are you sure you want to delete this scheduled routine?")) return;
      try {
        const res = await fetch(`/api/routines/${encodeURIComponent(taskId)}`, {
          method: "DELETE",
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        showToast("Routine deleted successfully", "info");
        await refreshAll();
      } catch (err) {
        console.error("Failed to delete routine:", err);
        showToast("Error deleting routine", "error");
      }
    } else if (action === "edit") {
      const routine = routinesData.find((r) => r.id === taskId);
      if (!routine) return;

      editTaskId.value = routine.id;
      editTaskTitle.value = routine.title;
      editTaskDomain.value = routine.domain || "routine";
      editTaskTime.value = routine.scheduled_time || "";
      editTaskRecurrence.value = routine.recurrence || "daily";

      editTaskDrawer.classList.remove("hidden");
      addTaskDrawer?.classList.add("hidden");
      editTaskDrawer.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  });

  // -------------------------------------------------------------------------
  // Ambient Stream Simulator Handlers
  // -------------------------------------------------------------------------

  presetButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      simInput.value = btn.dataset.text;
    });
  });

  btnRunSim?.addEventListener("click", async () => {
    const text = simInput.value.trim();
    if (!text) {
      showToast("Please enter an utterance to simulate.", "info");
      return;
    }

    btnRunSim.disabled = true;
    simSpinner.classList.remove("hidden");
    simOutputBox.classList.remove("hidden");
    simRawJson.textContent = "Streaming to Bedrock AgentCore pipeline...";

    try {
      const res = await fetch("/api/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          transcript_chunk: text,
          actor_id: "demo_user",
        }),
      });

      const data = await res.json();
      simLatency.textContent = `${data.elapsed_seconds || 0}s`;
      simRawJson.textContent = JSON.stringify(data, null, 2);

      if (data.success) {
        showToast("Utterance processed by AgentCore pipeline!", "success");
        await refreshAll();
      } else {
        showToast(`Simulation error: ${data.error}`, "error");
      }
    } catch (err) {
      console.error("Simulation request error:", err);
      simRawJson.textContent = `Error: ${err.message}`;
      showToast("Invocation failed. Check server logs.", "error");
    } finally {
      btnRunSim.disabled = false;
      simSpinner.classList.add("hidden");
    }
  });

  // -------------------------------------------------------------------------
  // Refresh Button & Auto-Sync
  // -------------------------------------------------------------------------

  btnRefresh?.addEventListener("click", async () => {
    btnRefresh.style.transform = "rotate(360deg)";
    await refreshAll();
    showToast("Dashboard synchronized with SQLite store.", "info");
    setTimeout(() => { btnRefresh.style.transform = ""; }, 400);
  });

  // -------------------------------------------------------------------------
  // Real-Time Server-Sent Events (SSE)
  // -------------------------------------------------------------------------
  function initSSE() {
    let evtSource = null;
    let reconnectTimeout = null;

    function connect() {
      if (evtSource) {
        evtSource.close();
      }

      try {
        evtSource = new EventSource("/api/events");

        evtSource.onopen = () => {
          console.log("SSE connection established with /api/events");
          isSSEConnected = true;
          elStatus.textContent = "Realtime Live";
          const pulse = document.querySelector(".live-indicator .pulse-dot");
          if (pulse) pulse.style.background = "#10b981";
        };

        evtSource.onmessage = (e) => {
          try {
            const payload = JSON.parse(e.data);
            console.log("SSE event received:", payload);

            if (payload.type === "pipeline_invoked") {
              showToast("New ambient audio verified by AgentCore!", "info");
              refreshAll();
            } else if (payload.type && payload.type.startsWith("routine_")) {
              refreshAll();
            }
          } catch (err) {
            // Keepalive or unparseable text
          }
        };

        evtSource.onerror = (err) => {
          console.warn("SSE connection interrupted, reconnecting...", err);
          isSSEConnected = false;
          elStatus.textContent = "Reconnecting...";
          const pulse = document.querySelector(".live-indicator .pulse-dot");
          if (pulse) pulse.style.background = "#f59e0b";
          evtSource.close();

          clearTimeout(reconnectTimeout);
          reconnectTimeout = setTimeout(connect, 3000);
        };
      } catch (err) {
        console.error("Failed to initialize SSE:", err);
      }
    }

    connect();
  }

  // Utility to prevent XSS
  function escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Initial load
  refreshAll();
  initSSE();

  // Background fallback poll every 15 seconds in case of network drops
  setInterval(refreshAll, 15000);
});
