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
  let commitmentsData = [];
  let activeCommitmentFilter = "all";
  let activeSubtab = "view-contacts";
  let activeEchoTemplate = "DEEP_BRIEFING_VIEWER";
  let currentDossierContact = null;
  let isSSEConnected = false;

  // DOM Elements - Telemetry & Header
  const elStatus = document.getElementById("telemetry-status");
  const elProvider = document.getElementById("telemetry-provider");
  const elModel = document.getElementById("telemetry-model");
  const btnRefresh = document.getElementById("btn-refresh");
  const btnOpenEchoModal = document.getElementById("btn-open-echo-modal");

  // DOM Elements - Badges
  const badgeActions = document.getElementById("badge-actions-count");
  const badgeRoutines = document.getElementById("badge-routines-count");
  const badgeSocial = document.getElementById("badge-social-count");
  const badgeBriefings = document.getElementById("badge-briefings-count");
  const badgeSubContacts = document.getElementById("badge-sub-contacts");
  const badgeSubCommitments = document.getElementById("badge-sub-commitments");
  const badgeSubDossiers = document.getElementById("badge-sub-dossiers");

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

  // DOM Elements - Social Sub-navigation & Panes
  const subnavTabs = document.querySelectorAll(".subnav-tab");
  const subtabPanes = document.querySelectorAll(".subtab-pane");
  const viewContacts = document.getElementById("view-contacts");
  const viewCommitments = document.getElementById("view-commitments");
  const viewDossiers = document.getElementById("view-dossiers");
  const commitmentsFullList = document.getElementById("commitments-full-list");
  const dossiersGrid = document.getElementById("dossiers-grid");

  // DOM Elements - Add Commitment Form
  const btnToggleAddCommitment = document.getElementById("btn-toggle-add-commitment");
  const addCommitmentDrawer = document.getElementById("add-commitment-drawer");
  const formAddCommitment = document.getElementById("form-add-commitment");
  const btnCancelCommitment = document.getElementById("btn-cancel-commitment");
  const comContactName = document.getElementById("com-contact-name");
  const comDebtor = document.getElementById("com-debtor");
  const comDesc = document.getElementById("com-desc");
  const comDueDate = document.getElementById("com-due-date");
  const comStatus = document.getElementById("com-status");
  const contactNamesList = document.getElementById("contact-names-list");

  // DOM Elements - Commitment Filters
  const filterPills = document.querySelectorAll(".filter-pill");
  const countCommAll = document.getElementById("count-comm-all");
  const countCommUser = document.getElementById("count-comm-user");
  const countCommContact = document.getElementById("count-comm-contact");
  const countCommDone = document.getElementById("count-comm-done");

  // DOM Elements - Executive Dossier Modal
  const modalExecutiveDossier = document.getElementById("modal-executive-dossier");
  const btnCloseDossier = document.getElementById("btn-close-dossier");
  const btnDossierCloseFooter = document.getElementById("btn-dossier-close-footer");
  const btnDossierRefresh = document.getElementById("btn-dossier-refresh");
  const btnDossierAddComm = document.getElementById("btn-dossier-add-comm");
  const modalDossierAvatar = document.getElementById("modal-dossier-avatar");
  const modalDossierName = document.getElementById("modal-dossier-name");
  const modalDossierRole = document.getElementById("modal-dossier-role");
  const modalDossierConf = document.getElementById("modal-dossier-conf");
  const modalDossierHeadline = document.getElementById("modal-dossier-headline");
  const modalDossierBio = document.getElementById("modal-dossier-bio");
  const modalDossierExpertise = document.getElementById("modal-dossier-expertise");
  const modalDossierLinks = document.getElementById("modal-dossier-links");
  const modalDossierCommitments = document.getElementById("modal-dossier-commitments");
  const modalDossierTopics = document.getElementById("modal-dossier-topics");

  // DOM Elements - Echo Show Preview Modal
  const modalEchoShow = document.getElementById("modal-echo-show");
  const btnCloseEcho = document.getElementById("btn-close-echo");
  const echoClock = document.getElementById("echo-clock");
  const echoCardCanvas = document.getElementById("echo-card-canvas");
  const echoVoiceText = document.getElementById("echo-voice-text");
  const echoTabBtns = document.querySelectorAll(".echo-tab-btn");

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

  function populateContactNamesDatalist(contacts) {
    if (!contactNamesList) return;
    contactNamesList.innerHTML = (contacts || [])
      .map(c => `<option value="${escapeHtml(c.name)}"></option>`)
      .join("");
  }

  async function fetchSocial() {
    try {
      const res = await fetch("/api/contacts");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      socialData = data.contacts || [];

      if (badgeSubContacts) badgeSubContacts.textContent = socialData.length;
      const enriched = socialData.filter(c => c.web_profile);
      if (badgeSubDossiers) badgeSubDossiers.textContent = enriched.length;

      populateContactNamesDatalist(socialData);
      renderSocial(socialData);
      renderDossiers(enriched);
    } catch (err) {
      console.error("Error fetching social contacts:", err);
      if (socialGrid) socialGrid.innerHTML = `<div class="empty-state">Failed to load social contacts.</div>`;
    }
  }

  async function fetchCommitments() {
    try {
      const res = await fetch("/api/commitments");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      commitmentsData = data.commitments || [];

      const allCount = commitmentsData.length;
      const userCount = commitmentsData.filter(c => c.debtor === "user" && c.status !== "fulfilled").length;
      const contactCount = commitmentsData.filter(c => c.debtor === "contact" && c.status !== "fulfilled").length;
      const doneCount = commitmentsData.filter(c => c.status === "fulfilled").length;

      if (countCommAll) countCommAll.textContent = allCount;
      if (countCommUser) countCommUser.textContent = userCount;
      if (countCommContact) countCommContact.textContent = contactCount;
      if (countCommDone) countCommDone.textContent = doneCount;
      if (badgeSubCommitments) badgeSubCommitments.textContent = allCount;

      renderCommitments(commitmentsData, activeCommitmentFilter);
    } catch (err) {
      console.error("Error fetching commitments:", err);
      if (commitmentsFullList) commitmentsFullList.innerHTML = `<div class="empty-state">Failed to load bilateral commitments.</div>`;
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
      fetchCommitments(),
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
      const isAmbient = r.origin === "ambient_voice";
      const originBadge = isAmbient
        ? `<span class="routine-origin-badge">🎙️ Ambient Voice</span>`
        : "";
      const heardText = r.raw_statement
        ? `<div class="routine-heard-text">🎙️ Spoken: "${escapeHtml(r.raw_statement)}"</div>`
        : "";
      const anchorText = r.relative_time_anchor
        ? `<span>Anchor: <strong>${escapeHtml(r.relative_time_anchor)}</strong></span>`
        : "";

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
                ${originBadge}
                ${r.scheduled_time ? `<span>Target: <strong>${escapeHtml(r.scheduled_time)}</strong></span>` : ""}
                ${anchorText}
                <span>Recurrence: <strong>${escapeHtml(r.recurrence)}</strong></span>
                ${isCompleted && r.completed_at ? `<span>Completed at: <strong class="highlight-text">${escapeHtml(r.completed_at)}</strong></span>` : ""}
              </div>
              ${heardText}
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

      let commitmentsHtml = "";
      if (c.commitments && c.commitments.length > 0) {
        const itemsHtml = c.commitments.map((item) => {
          let desc = "";
          let debtor = "user";
          let status = "open";
          let deadline = "";
          let id = "";

          if (typeof item === "string") {
            desc = item;
            const isUser = /^(i\s|i'll\s|i\s+will\s|let\s+me\s|ti\s+mando|ti\s+invio)/i.test(item.trim());
            debtor = isUser ? "user" : "contact";
          } else if (typeof item === "object" && item !== null) {
            desc = item.description || "";
            debtor = item.debtor || "user";
            status = item.status || "open";
            deadline = item.due_date_raw || "";
            id = item.id || "";
          }

          const debtorBadge = debtor === "user"
            ? `<span class="debtor-badge debtor-user">📤 You Promised</span>`
            : `<span class="debtor-badge debtor-contact">📥 Contact Promised</span>`;

          const deadlineBadge = deadline
            ? `<span class="commitment-deadline">⏱️ ${escapeHtml(deadline)}</span>`
            : "";

          const isDone = status === "fulfilled";
          const actionBtn = (!isDone && id)
            ? `<button class="btn-fulfill-commitment" data-id="${escapeHtml(id)}">✓ Done</button>`
            : (isDone ? `<span style="font-size:0.75rem; color:#34d399; font-weight:600;">✓ Done</span>` : "");

          return `
            <li class="commitment-item ${isDone ? 'status-fulfilled' : ''}">
              <div class="commitment-main">
                <div class="commitment-tags-row">
                  ${debtorBadge}
                  ${deadlineBadge}
                </div>
                <div class="commitment-desc ${isDone ? 'strikethrough' : ''}">${escapeHtml(desc)}</div>
              </div>
              <div>
                ${actionBtn}
              </div>
            </li>
          `;
        }).join("");

        commitmentsHtml = `
          <div class="social-commitments-box">
            <div class="commitments-header">
              <span>📌 Bilateral Commitments (${c.commitments.length})</span>
            </div>
            <ul class="commitments-list">
              ${itemsHtml}
            </ul>
          </div>
        `;
      }

      const wp = c.web_profile;
      let webProfileHtml = "";
      if (wp) {
        const headlineHtml = wp.headline ? `<div class="social-wp-headline">${escapeHtml(wp.headline)}</div>` : "";
        const bioHtml = wp.bio_summary ? `<div class="social-wp-bio">${escapeHtml(wp.bio_summary)}</div>` : "";
        const expertisePills = (wp.areas_of_expertise || []).map((exp) => 
          `<span class="expertise-pill">🎯 ${escapeHtml(exp)}</span>`
        ).join("");

        let linksHtml = "";
        if (wp.linkedin_url) {
          linksHtml += `<a href="${escapeHtml(wp.linkedin_url)}" target="_blank" rel="noopener noreferrer" class="social-link-pill linkedin-pill">💼 LinkedIn</a>`;
        }
        if (wp.github_url) {
          linksHtml += `<a href="${escapeHtml(wp.github_url)}" target="_blank" rel="noopener noreferrer" class="social-link-pill github-pill">🐙 GitHub</a>`;
        }
        if (wp.website_url) {
          linksHtml += `<a href="${escapeHtml(wp.website_url)}" target="_blank" rel="noopener noreferrer" class="social-link-pill web-pill">🌐 Website</a>`;
        }

        webProfileHtml = `
          <div class="social-web-profile-card">
            <div class="social-wp-header">
              <span class="badge-verified">⚡ Executive Web Intelligence</span>
              ${wp.confidence_score ? `<span class="wp-confidence">${Math.round(wp.confidence_score * 100)}% Match</span>` : ""}
            </div>
            ${headlineHtml}
            ${bioHtml}
            ${expertisePills ? `<div class="social-expertise-row">${expertisePills}</div>` : ""}
            ${linksHtml ? `<div class="social-links-row">${linksHtml}</div>` : ""}
          </div>
        `;
      }

      const enrichBtn = `
        <button class="btn-enrich-contact ${wp ? 'btn-reenrich' : ''}" data-id="${escapeHtml(c.id || c.name)}" title="Autonomously research public professional background on the web">
          ${wp ? '🔄 Refresh Intelligence' : '⚡ Enrich Profile'}
        </button>
      `;

      return `
        <div class="social-card" data-id="${escapeHtml(c.id || c.name)}">
          <div class="card-title clickable-contact" data-id="${escapeHtml(c.id || c.name)}" title="Click to view full executive dossier">
            ${escapeHtml(c.name)}
          </div>
          <div class="card-role">${escapeHtml(c.company_or_role || 'Independent / Contact')}</div>
          ${topicsHtml ? `<div class="social-topics-tags">${topicsHtml}</div>` : ""}
          ${webProfileHtml}
          ${commitmentsHtml}
          <div class="social-card-actions">
            ${wp ? `<button class="btn-primary btn-sm btn-view-dossier" data-id="${escapeHtml(c.id || c.name)}" title="Open executive dossier modal">👁️ View Dossier</button>` : ""}
            ${enrichBtn}
            <span style="font-size: 0.72rem; color: #64748b;">${wp ? 'Verified Web Dossier' : 'Unenriched'}</span>
          </div>
          <div class="card-footer">
            <span>First met: ${c.timestamp ? c.timestamp.split("T")[0] : "-"}</span>
            ${c.contact_info ? `<span>${escapeHtml(c.contact_info)}</span>` : ""}
          </div>
        </div>
      `;
    }).join("");
  }

  function renderCommitments(commitments, filter = "all") {
    if (!commitmentsFullList) return;
    if (!commitments || commitments.length === 0) {
      commitmentsFullList.innerHTML = `<div class="empty-state">No bilateral commitments recorded yet. Capture them automatically from conversation or click '+ New Commitment' above!</div>`;
      return;
    }

    let filtered = [...commitments];
    if (filter === "user") {
      filtered = filtered.filter(c => c.debtor === "user" && c.status !== "fulfilled");
    } else if (filter === "contact") {
      filtered = filtered.filter(c => c.debtor === "contact" && c.status !== "fulfilled");
    } else if (filter === "fulfilled") {
      filtered = filtered.filter(c => c.status === "fulfilled");
    }

    if (filtered.length === 0) {
      commitmentsFullList.innerHTML = `<div class="empty-state">No commitments matching filter '${filter}'.</div>`;
      return;
    }

    commitmentsFullList.innerHTML = filtered.map(c => {
      const isDone = c.status === "fulfilled";
      const isUser = c.debtor === "user";
      const debtorClass = isUser ? "debtor-user" : "debtor-contact";
      const debtorBadge = isUser
        ? `<span class="debtor-badge debtor-user">📤 You Promised</span>`
        : `<span class="debtor-badge debtor-contact">📥 Contact Promised</span>`;
      const deadlineBadge = c.due_date_raw
        ? `<span class="commitment-deadline">⏱️ ${escapeHtml(c.due_date_raw)}</span>`
        : "";
      const statusBadge = isDone
        ? `<span class="conf-pill" style="color: #34d399; border-color: rgba(16, 185, 129, 0.4);">✓ Fulfilled</span>`
        : `<span class="conf-pill" style="color: #fbbf24; border-color: rgba(245, 158, 11, 0.4);">⏳ Open</span>`;
      const routineLink = (c.auto_scheduled_task_id && isUser)
        ? `<div style="font-size:0.75rem; color:#a78bfa;">🔗 Linked Routine #${escapeHtml(c.auto_scheduled_task_id.slice(0, 8))}</div>`
        : "";

      const fulfillBtn = !isDone
        ? `<button class="btn-card-fulfill" data-id="${escapeHtml(c.id)}">✓ Mark Done</button>`
        : `<span style="font-size:0.8rem; color:#34d399; font-weight:600;">✓ Completed</span>`;

      return `
        <div class="commitment-card-full ${debtorClass} ${isDone ? 'status-fulfilled' : ''}" data-id="${escapeHtml(c.id)}">
          <div class="commitment-card-header">
            <span class="commitment-contact-link" data-name="${escapeHtml(c.contact_name)}">👤 ${escapeHtml(c.contact_name)}</span>
            <div style="display:flex; gap:0.4rem; align-items:center;">
              ${debtorBadge}
              ${statusBadge}
            </div>
          </div>
          <div class="commitment-full-desc">
            "${escapeHtml(c.description)}"
          </div>
          <div class="commitment-meta-row">
            ${deadlineBadge}
            ${routineLink}
            <span>Created: ${c.created_at ? c.created_at.split("T")[0] : "-"}</span>
          </div>
          <div class="commitment-card-actions">
            <div>${fulfillBtn}</div>
            <button class="btn-card-delete" data-id="${escapeHtml(c.id)}" title="Delete commitment">🗑️</button>
          </div>
        </div>
      `;
    }).join("");
  }

  function renderDossiers(dossiers) {
    if (!dossiersGrid) return;
    if (!dossiers || dossiers.length === 0) {
      dossiersGrid.innerHTML = `<div class="empty-state">No executive dossiers enriched yet. Click '⚡ Enrich Profile' on contacts to corroborate them with web intelligence!</div>`;
      return;
    }

    dossiersGrid.innerHTML = dossiers.map(c => {
      const wp = c.web_profile;
      const initials = c.name.split(" ").map(n => n[0]).slice(0, 2).join("").toUpperCase();
      const expertisePills = (wp.areas_of_expertise || []).map(exp =>
        `<span class="expertise-pill">🎯 ${escapeHtml(exp)}</span>`
      ).join("");

      let linksHtml = "";
      if (wp.linkedin_url) linksHtml += `<a href="${escapeHtml(wp.linkedin_url)}" target="_blank" rel="noopener noreferrer" class="social-link-pill linkedin-pill">💼 LinkedIn</a>`;
      if (wp.github_url) linksHtml += `<a href="${escapeHtml(wp.github_url)}" target="_blank" rel="noopener noreferrer" class="social-link-pill github-pill">🐙 GitHub</a>`;
      if (wp.website_url) linksHtml += `<a href="${escapeHtml(wp.website_url)}" target="_blank" rel="noopener noreferrer" class="social-link-pill web-pill">🌐 Website</a>`;

      return `
        <div class="social-card executive-card" style="border-color: rgba(139, 92, 246, 0.4);">
          <div style="display: flex; align-items: center; justify-content: space-between;">
            <div style="display:flex; align-items:center; gap:0.75rem;">
              <div class="dossier-avatar" style="width:42px; height:42px; font-size:1.1rem;">${initials}</div>
              <div>
                <div class="card-title clickable-contact" data-id="${escapeHtml(c.id || c.name)}">${escapeHtml(c.name)}</div>
                <div class="card-role">${escapeHtml(wp.organization || c.company_or_role || '')}</div>
              </div>
            </div>
            ${wp.confidence_score ? `<span class="badge-verified">⚡ ${Math.round(wp.confidence_score * 100)}% Verified</span>` : ""}
          </div>
          ${wp.headline ? `<div class="social-wp-headline">${escapeHtml(wp.headline)}</div>` : ""}
          ${wp.bio_summary ? `<div class="social-wp-bio">${escapeHtml(wp.bio_summary)}</div>` : ""}
          ${expertisePills ? `<div class="social-expertise-row">${expertisePills}</div>` : ""}
          ${linksHtml ? `<div class="social-links-row">${linksHtml}</div>` : ""}
          <div class="social-card-actions" style="margin-top:0.75rem;">
            <button class="btn-primary btn-sm btn-view-dossier" data-id="${escapeHtml(c.id || c.name)}">
              👁️ View Full Dossier
            </button>
            <button class="btn-enrich-contact btn-reenrich" data-id="${escapeHtml(c.id || c.name)}">
              🔄 Refresh
            </button>
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
  // Subnav Navigation (All Contacts, Bilateral Commitments, Executive Dossiers)
  // -------------------------------------------------------------------------
  subnavTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const targetSubtab = tab.dataset.subtab;
      activeSubtab = targetSubtab;
      subnavTabs.forEach((t) => t.classList.remove("active"));
      subtabPanes.forEach((p) => {
        p.classList.remove("active");
        p.classList.add("hidden");
      });
      tab.classList.add("active");
      const targetPane = document.getElementById(targetSubtab);
      if (targetPane) {
        targetPane.classList.remove("hidden");
        targetPane.classList.add("active");
      }
    });
  });

  // -------------------------------------------------------------------------
  // Commitments Filter Pills
  // -------------------------------------------------------------------------
  filterPills.forEach((pill) => {
    pill.addEventListener("click", () => {
      filterPills.forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      activeCommitmentFilter = pill.dataset.filter || "all";
      renderCommitments(commitmentsData, activeCommitmentFilter);
    });
  });

  // -------------------------------------------------------------------------
  // Add Commitment Drawer Handlers
  // -------------------------------------------------------------------------
  btnToggleAddCommitment?.addEventListener("click", () => {
    addCommitmentDrawer?.classList.toggle("hidden");
    if (!addCommitmentDrawer?.classList.contains("hidden")) {
      comContactName?.focus();
    }
  });

  btnCancelCommitment?.addEventListener("click", () => {
    addCommitmentDrawer?.classList.add("hidden");
  });

  formAddCommitment?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const contact_name = comContactName.value.trim();
    const debtor = comDebtor.value;
    const description = comDesc.value.trim();
    const due_date_raw = comDueDate.value.trim();
    const status = comStatus.value;

    if (!contact_name || !description) return;

    try {
      const res = await fetch("/api/commitments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contact_name,
          debtor,
          description,
          due_date_raw,
          status,
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showToast(`Commitment recorded for ${contact_name}!`, "success");
      formAddCommitment.reset();
      addCommitmentDrawer?.classList.add("hidden");
      await fetchCommitments();
      await fetchSocial();
      await fetchRoutines();
    } catch (err) {
      console.error("Failed to add commitment:", err);
      showToast("Error creating commitment.", "error");
    }
  });

  // -------------------------------------------------------------------------
  // Commitments Board Event Delegation (Fulfill, Delete, Contact Click)
  // -------------------------------------------------------------------------
  commitmentsFullList?.addEventListener("click", async (e) => {
    const fulfillBtn = e.target.closest(".btn-card-fulfill");
    if (fulfillBtn) {
      const comId = fulfillBtn.dataset.id;
      if (!comId) return;
      fulfillBtn.disabled = true;
      fulfillBtn.textContent = "...";
      try {
        const res = await fetch(`/api/commitments/${encodeURIComponent(comId)}/fulfill`, { method: "POST" });
        if (res.ok) {
          showToast("Commitment fulfilled!", "success");
          await fetchCommitments();
          await fetchSocial();
          await fetchRoutines();
        } else {
          showToast("Failed to fulfill commitment", "error");
          fulfillBtn.disabled = false;
          fulfillBtn.textContent = "✓ Mark Done";
        }
      } catch (err) {
        console.error(err);
        showToast("Network error", "error");
        fulfillBtn.disabled = false;
        fulfillBtn.textContent = "✓ Mark Done";
      }
      return;
    }

    const deleteBtn = e.target.closest(".btn-card-delete");
    if (deleteBtn) {
      const comId = deleteBtn.dataset.id;
      if (!comId) return;
      if (!confirm("Are you sure you want to delete this bilateral commitment?")) return;
      try {
        const res = await fetch(`/api/commitments/${encodeURIComponent(comId)}`, { method: "DELETE" });
        if (res.ok) {
          showToast("Commitment deleted", "info");
          await fetchCommitments();
          await fetchSocial();
          await fetchRoutines();
        } else {
          showToast("Failed to delete commitment", "error");
        }
      } catch (err) {
        console.error(err);
        showToast("Error deleting commitment", "error");
      }
      return;
    }

    const contactLink = e.target.closest(".commitment-contact-link");
    if (contactLink) {
      const name = contactLink.dataset.name;
      if (name) openDossierModal(name);
      return;
    }
  });

  // Social Grid In-Card Fulfill Handler
  socialGrid?.addEventListener("click", async (e) => {
    const btn = e.target.closest(".btn-fulfill-commitment");
    if (!btn) return;
    const comId = btn.dataset.id;
    if (!comId) return;
    btn.disabled = true;
    btn.textContent = "...";
    try {
      const res = await fetch(`/api/commitments/${encodeURIComponent(comId)}/fulfill`, { method: "POST" });
      if (res.ok) {
        showToast("Commitment marked fulfilled!", "success");
        await fetchSocial();
        await fetchCommitments();
        await fetchRoutines();
      } else {
        showToast("Failed to fulfill commitment", "error");
        btn.disabled = false;
        btn.textContent = "✓ Done";
      }
    } catch (err) {
      console.error(err);
      showToast("Network error", "error");
      btn.disabled = false;
      btn.textContent = "✓ Done";
    }
  });

  // -------------------------------------------------------------------------
  // Milestone 2.1: Social Contact Autonomous Profiler Trigger Handler
  // -------------------------------------------------------------------------
  socialGrid?.addEventListener("click", async (e) => {
    const btn = e.target.closest(".btn-enrich-contact");
    if (!btn) return;
    const contactId = btn.dataset.id;
    if (!contactId) return;

    btn.disabled = true;
    const origHtml = btn.innerHTML;
    btn.innerHTML = `<span>⏳ Researching Web...</span>`;

    try {
      const res = await fetch(`/api/contacts/${encodeURIComponent(contactId)}/enrich`, { method: "POST" });
      const data = await res.json();
      if (res.ok && data.success) {
        showToast(data.message || "Contact dossier enriched from web intelligence!", "success");
        await fetchSocial();
        await fetchCommitments();
      } else {
        showToast(data.message || "Could not enrich contact (insufficient disambiguation anchors or no results).", "warning");
        btn.disabled = false;
        btn.innerHTML = origHtml;
      }
    } catch (err) {
      console.error(err);
      showToast("Network error while researching contact profile.", "error");
      btn.disabled = false;
      btn.innerHTML = origHtml;
    }
  });

  // -------------------------------------------------------------------------
  // Executive Dossier Modal Handlers
  // -------------------------------------------------------------------------
  function openDossierModal(idOrName) {
    if (!idOrName) return;
    const contact = socialData.find(
      (c) => (c.id && c.id === idOrName) || c.name.toLowerCase() === idOrName.toLowerCase()
    );
    if (!contact) {
      showToast(`Contact "${idOrName}" not found in current session`, "info");
      return;
    }
    currentDossierContact = contact;

    const initials = contact.name.split(" ").map((n) => n[0]).slice(0, 2).join("").toUpperCase();
    if (modalDossierAvatar) modalDossierAvatar.textContent = initials;
    if (modalDossierName) modalDossierName.textContent = contact.name;
    if (modalDossierRole) modalDossierRole.textContent = contact.company_or_role || "Professional Contact";

    const wp = contact.web_profile;
    if (modalDossierConf) {
      if (wp && wp.confidence_score) {
        modalDossierConf.textContent = `⚡ ${Math.round(wp.confidence_score * 100)}% Match`;
        modalDossierConf.style.display = "inline-flex";
      } else {
        modalDossierConf.textContent = wp ? "⚡ Web Verified" : "Unverified";
        modalDossierConf.style.display = wp ? "inline-flex" : "none";
      }
    }

    if (modalDossierHeadline) {
      modalDossierHeadline.textContent = (wp && wp.headline) ? wp.headline : "Executive contact recorded in conversation.";
    }

    if (modalDossierBio) {
      modalDossierBio.textContent = (wp && wp.bio_summary) ? wp.bio_summary : "Run web intelligence enrichment to autonomously research public professional background.";
    }

    if (modalDossierExpertise) {
      if (wp && wp.areas_of_expertise && wp.areas_of_expertise.length > 0) {
        modalDossierExpertise.innerHTML = wp.areas_of_expertise
          .map((exp) => `<span class="expertise-pill">🎯 ${escapeHtml(exp)}</span>`)
          .join("");
      } else {
        modalDossierExpertise.innerHTML = `<span style="font-size:0.8rem; color:#64748b;">No expertise tags extracted yet.</span>`;
      }
    }

    if (modalDossierLinks) {
      let linksHtml = "";
      if (wp && wp.linkedin_url) linksHtml += `<a href="${escapeHtml(wp.linkedin_url)}" target="_blank" rel="noopener noreferrer" class="social-link-pill linkedin-pill">💼 LinkedIn</a>`;
      if (wp && wp.github_url) linksHtml += `<a href="${escapeHtml(wp.github_url)}" target="_blank" rel="noopener noreferrer" class="social-link-pill github-pill">🐙 GitHub</a>`;
      if (wp && wp.website_url) linksHtml += `<a href="${escapeHtml(wp.website_url)}" target="_blank" rel="noopener noreferrer" class="social-link-pill web-pill">🌐 Website</a>`;
      modalDossierLinks.innerHTML = linksHtml || `<span style="font-size:0.8rem; color:#64748b;">No external web links discovered.</span>`;
    }

    if (modalDossierCommitments) {
      const comms = (contact.commitments || []).map((item) => {
        if (typeof item === "string") return { description: item, debtor: "user", status: "open" };
        return item;
      });
      if (comms.length === 0) {
        modalDossierCommitments.innerHTML = `<li style="color:#64748b; font-size:0.82rem;">No bilateral commitments recorded with ${escapeHtml(contact.name)}.</li>`;
      } else {
        modalDossierCommitments.innerHTML = comms.map((c) => {
          const isDone = c.status === "fulfilled";
          const badge = c.debtor === "user" ? "📤 You Promised" : "📥 Contact Promised";
          return `
            <li class="commitment-item ${isDone ? 'status-fulfilled' : ''}" style="margin-bottom:0.4rem;">
              <div class="commitment-main">
                <span class="debtor-badge ${c.debtor === 'user' ? 'debtor-user' : 'debtor-contact'}">${badge}</span>
                <span class="${isDone ? 'strikethrough' : ''}">${escapeHtml(c.description)}</span>
              </div>
            </li>
          `;
        }).join("");
      }
    }

    if (modalDossierTopics) {
      if (contact.key_topics && contact.key_topics.length > 0) {
        modalDossierTopics.innerHTML = contact.key_topics
          .map((t) => `<span class="topic-tag">#${escapeHtml(t)}</span>`)
          .join("");
      } else {
        modalDossierTopics.innerHTML = `<span style="font-size:0.8rem; color:#64748b;">No conversation topics logged.</span>`;
      }
    }

    modalExecutiveDossier?.classList.remove("hidden");
  }

  function closeDossierModal() {
    modalExecutiveDossier?.classList.add("hidden");
    currentDossierContact = null;
  }

  btnCloseDossier?.addEventListener("click", closeDossierModal);
  btnDossierCloseFooter?.addEventListener("click", closeDossierModal);
  modalExecutiveDossier?.addEventListener("click", (e) => {
    if (e.target === modalExecutiveDossier) closeDossierModal();
  });

  btnDossierRefresh?.addEventListener("click", async () => {
    if (!currentDossierContact) return;
    btnDossierRefresh.disabled = true;
    btnDossierRefresh.textContent = "⏳ Enriching...";
    try {
      const res = await fetch(`/api/contacts/${encodeURIComponent(currentDossierContact.id || currentDossierContact.name)}/enrich`, { method: "POST" });
      const data = await res.json();
      if (res.ok && data.success) {
        showToast("Dossier refreshed from web intelligence!", "success");
        await fetchSocial();
        openDossierModal(currentDossierContact.name);
      } else {
        showToast(data.message || "Enrichment completed without changes.", "warning");
      }
    } catch (err) {
      console.error(err);
      showToast("Error updating dossier.", "error");
    } finally {
      btnDossierRefresh.disabled = false;
      btnDossierRefresh.textContent = "⚡ Refresh Web Intelligence";
    }
  });

  btnDossierAddComm?.addEventListener("click", () => {
    if (!currentDossierContact) return;
    const name = currentDossierContact.name;
    closeDossierModal();
    const socialTab = document.querySelector('.nav-tab[data-tab="tab-social"]');
    if (socialTab) socialTab.click();
    const commSubtab = document.getElementById("subtab-commitments");
    if (commSubtab) commSubtab.click();

    addCommitmentDrawer?.classList.remove("hidden");
    if (comContactName) comContactName.value = name;
    if (comDesc) comDesc.focus();
  });

  // Delegated clicks for opening dossier modal from social grid and dossiers grid
  document.addEventListener("click", (e) => {
    const viewBtn = e.target.closest(".btn-view-dossier");
    if (viewBtn) {
      const id = viewBtn.dataset.id;
      if (id) openDossierModal(id);
      return;
    }
    const clickable = e.target.closest(".clickable-contact");
    if (clickable) {
      const id = clickable.dataset.id;
      if (id) openDossierModal(id);
      return;
    }
  });

  // -------------------------------------------------------------------------
  // Echo Show Multi-Modal Device & Touch Card Canvas Handlers
  // -------------------------------------------------------------------------
  let echoClockInterval = null;

  function updateEchoClock() {
    if (!echoClock) return;
    const now = new Date();
    const hrs = String(now.getHours()).padStart(2, "0");
    const mins = String(now.getMinutes()).padStart(2, "0");
    echoClock.textContent = `${hrs}:${mins}`;
  }

  async function renderEchoCard(templateKey) {
    if (!echoCardCanvas) return;
    activeEchoTemplate = templateKey || "DEEP_BRIEFING_VIEWER";

    echoTabBtns.forEach((btn) => {
      if (btn.dataset.template === activeEchoTemplate) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });

    echoCardCanvas.innerHTML = `<div class="echo-card-loading">Loading Echo Show Touch Card...</div>`;

    try {
      const res = await fetch(`/api/cards/preview?template=${encodeURIComponent(activeEchoTemplate)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const card = await res.json();

      if (echoVoiceText) {
        echoVoiceText.textContent = `"${card.spoken_summary || 'Here is your update.'}"`;
      }

      const p = card.card_payload || {};

      switch (card.display_template) {
        case "DEEP_BRIEFING_VIEWER": {
          const bullets = (p.bullets || []).map((b) => `<li>${escapeHtml(b)}</li>`).join("");
          const sources = (p.sources || []).map((s) => `<a href="${escapeHtml(s)}" target="_blank" rel="noopener noreferrer" class="source-link" style="color:#60a5fa;">🔗 ${escapeHtml(s.replace(/https?:\/\/(www\.)?/, '').slice(0, 24))}</a>`).join("");
          echoCardCanvas.innerHTML = `
            <div class="echo-card-inner">
              <div class="echo-card-category">${escapeHtml((p.context_type || "Technical Briefing").toUpperCase())}</div>
              <h2 class="echo-card-headline">${escapeHtml(p.topic_title || "Technical Synthesis")}</h2>
              <ul class="echo-bullet-list">
                ${bullets || '<li>Executive summary extracted autonomously.</li>'}
              </ul>
              ${p.synthesis ? `
                <div class="briefing-explanatory-box" style="margin-top:0.6rem; padding:0.6rem; font-size:0.85rem;">
                  <div style="font-weight:600; color:#38bdf8; margin-bottom:0.2rem;">💡 Contextual Synthesis:</div>
                  <div>${escapeHtml(p.synthesis)}</div>
                </div>
              ` : ''}
              ${sources ? `<div style="margin-top:0.6rem; font-size:0.75rem; color:#94a3b8; display:flex; gap:0.4rem; flex-wrap:wrap; align-items:center;"><span>Sources:</span> ${sources}</div>` : ''}
            </div>
          `;
          break;
        }

        case "SOCIAL_PROFILE_CARD": {
          const expertise = (p.expertise || []).map((exp) => `<span class="expertise-pill">🎯 ${escapeHtml(exp)}</span>`).join("");
          let links = "";
          if (p.linkedin) links += `<a href="${escapeHtml(p.linkedin)}" target="_blank" rel="noopener noreferrer" class="social-link-pill linkedin-pill">💼 LinkedIn</a>`;
          if (p.github) links += `<a href="${escapeHtml(p.github)}" target="_blank" rel="noopener noreferrer" class="social-link-pill github-pill">🐙 GitHub</a>`;
          if (p.website) links += `<a href="${escapeHtml(p.website)}" target="_blank" rel="noopener noreferrer" class="social-link-pill web-pill">🌐 Website</a>`;
          const commsList = (p.commitments || []).map((c) => {
            const desc = typeof c === "string" ? c : (c.description || "");
            const debtor = typeof c === "object" ? (c.debtor === "user" ? "📤 You" : "📥 Contact") : "📤 You";
            return `<li><span class="debtor-badge" style="padding:1px 4px; font-size:0.65rem;">${debtor}</span> ${escapeHtml(desc)}</li>`;
          }).join("");

          echoCardCanvas.innerHTML = `
            <div class="echo-card-inner">
              <div style="display:flex; align-items:center; gap:0.8rem; margin-bottom:0.6rem;">
                <div class="dossier-avatar" style="width:48px; height:48px; font-size:1.2rem;">
                  ${escapeHtml((p.name || 'C').slice(0, 2).toUpperCase())}
                </div>
                <div>
                  <h2 class="echo-card-headline" style="margin:0; font-size:1.2rem;">${escapeHtml(p.name || 'Executive Contact')}</h2>
                  <div class="echo-card-category" style="margin:0;">${escapeHtml(p.headline || p.company_or_role || 'Verified Contact')}</div>
                </div>
                ${p.confidence ? `<span class="badge-verified" style="margin-left:auto;">⚡ ${Math.round(p.confidence * 100)}%</span>` : ''}
              </div>
              <div style="font-size:0.88rem; line-height:1.4; color:#cbd5e1; margin-bottom:0.6rem;">
                ${escapeHtml(p.bio || 'Public executive intelligence extracted via Tavily.')}
              </div>
              ${expertise ? `<div class="social-expertise-row" style="margin-bottom:0.6rem;">${expertise}</div>` : ''}
              ${links ? `<div class="social-links-row" style="margin-bottom:0.6rem;">${links}</div>` : ''}
              ${commsList ? `
                <div class="social-commitments-box" style="margin-top:0.4rem; padding:0.5rem;">
                  <div class="commitments-header" style="font-size:0.75rem;">📌 Bilateral Commitments:</div>
                  <ul class="commitments-list" style="font-size:0.8rem; margin:0.3rem 0 0 0; padding-left:1.2rem;">${commsList}</ul>
                </div>
              ` : ''}
            </div>
          `;
          break;
        }

        case "SOCIAL_COMMITMENTS_CARD": {
          const debts = (p.user_debts || []).map((d) => `
            <li class="commitment-item" style="padding:0.4rem 0.6rem; margin-bottom:0.3rem;">
              <span class="debtor-badge debtor-user">📤 You Promised</span>
              <span style="font-size:0.85rem;">${escapeHtml(d.description)}</span>
              ${d.due_date ? `<span class="commitment-deadline" style="margin-left:auto;">⏱️ ${escapeHtml(d.due_date)}</span>` : ''}
            </li>
          `).join("");

          const claims = (p.contact_promises || []).map((c) => `
            <li class="commitment-item" style="padding:0.4rem 0.6rem; margin-bottom:0.3rem;">
              <span class="debtor-badge debtor-contact">📥 Contact Promised</span>
              <span style="font-size:0.85rem;">${escapeHtml(c.description)}</span>
              ${c.due_date ? `<span class="commitment-deadline" style="margin-left:auto;">⏱️ ${escapeHtml(c.due_date)}</span>` : ''}
            </li>
          `).join("");

          echoCardCanvas.innerHTML = `
            <div class="echo-card-inner">
              <div class="echo-card-category">BILATERAL SOCIAL PROMISES</div>
              <h2 class="echo-card-headline" style="font-size:1.15rem; margin-bottom:0.6rem;">
                ${escapeHtml(p.contact_name ? `Active Commitments with ${p.contact_name}` : 'Peace of Mind Commitments')}
              </h2>
              <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.6rem;">
                <div>
                  <div style="font-size:0.75rem; font-weight:700; color:#f87171; margin-bottom:0.3rem; text-transform:uppercase;">
                    📤 Your Promises (${p.total_user_debts || 0})
                  </div>
                  <ul class="commitments-list" style="margin:0; padding:0; list-style:none;">
                    ${debts || '<li style="font-size:0.8rem; color:#64748b;">No active debts you owe.</li>'}
                  </ul>
                </div>
                <div>
                  <div style="font-size:0.75rem; font-weight:700; color:#60a5fa; margin-bottom:0.3rem; text-transform:uppercase;">
                    📥 Owed to You (${p.total_contact_promises || 0})
                  </div>
                  <ul class="commitments-list" style="margin:0; padding:0; list-style:none;">
                    ${claims || '<li style="font-size:0.8rem; color:#64748b;">No promises from contacts.</li>'}
                  </ul>
                </div>
              </div>
            </div>
          `;
          break;
        }

        case "ACTION_VERIFIED_BADGE": {
          echoCardCanvas.innerHTML = `
            <div class="echo-card-inner" style="display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; padding:1.5rem 1rem;">
              <div style="width:72px; height:72px; border-radius:50%; background:linear-gradient(135deg, #059669, #10b981); display:flex; align-items:center; justify-content:center; font-size:2.4rem; box-shadow:0 0 24px rgba(16,185,129,0.5); margin-bottom:0.8rem;">
                ✓
              </div>
              <div class="echo-card-category" style="color:#34d399; letter-spacing:0.1em;">PEACE OF MIND VERIFIED</div>
              <h2 class="echo-card-headline" style="font-size:1.4rem; margin-bottom:0.4rem;">
                ${escapeHtml(p.action_type ? p.action_type.replace(/_/g, " ").toUpperCase() : "ACTION CONFIRMED")}
              </h2>
              <div style="font-size:0.95rem; color:#94a3b8; font-style:italic; max-width:440px; margin-bottom:0.6rem;">
                "${escapeHtml(p.raw_statement || 'Verified from ambient acoustic stream')}"
              </div>
              <div style="display:flex; gap:0.6rem; align-items:center;">
                <span class="conf-pill" style="font-size:0.85rem; padding:0.25rem 0.6rem;">
                  ⏱️ ${escapeHtml(p.elapsed_time || 'Just now')}
                </span>
                <span class="badge-verified" style="font-size:0.85rem; padding:0.25rem 0.6rem;">
                  ✓ ${Math.round((p.confidence || 0.95) * 100)}% Confidence
                </span>
              </div>
            </div>
          `;
          break;
        }

        case "DAILY_ACTIONS_RECAP": {
          const actionsList = (p.recent_actions || []).map((a) => `
            <div class="action-card" style="padding:0.5rem; margin-bottom:0.3rem;">
              <div style="display:flex; justify-content:space-between; font-size:0.75rem; color:#94a3b8;">
                <span class="card-badge badge-${escapeHtml(a.domain || 'safety')}">${escapeHtml(a.domain || 'safety')}</span>
                <span>${escapeHtml(a.elapsed_time || '')}</span>
              </div>
              <div style="font-size:0.85rem; font-weight:600; color:#f1f5f9; margin-top:0.2rem;">
                ${escapeHtml(a.action_type.replace(/_/g, ' '))}
              </div>
            </div>
          `).join("");

          echoCardCanvas.innerHTML = `
            <div class="echo-card-inner">
              <div class="echo-card-category">DAILY PEACE OF MIND RECAP</div>
              <h2 class="echo-card-headline" style="font-size:1.15rem; margin-bottom:0.4rem;">
                ${p.total_actions || 0} Actions Verified Today
              </h2>
              <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.8rem; margin-top:0.4rem;">
                <div>
                  <div style="font-size:0.75rem; font-weight:700; color:#34d399; text-transform:uppercase; margin-bottom:0.3rem;">
                    Completed Tasks (${p.completed_tasks_count || 0})
                  </div>
                  <div style="font-size:0.82rem; color:#cbd5e1;">
                    ${p.tasks_count || 0} routines registered in peace of mind watcher.
                  </div>
                </div>
                <div>
                  <div style="font-size:0.75rem; font-weight:700; color:#60a5fa; text-transform:uppercase; margin-bottom:0.3rem;">
                    Recent Acoustic Triggers
                  </div>
                  <div style="max-height:160px; overflow-y:auto;">
                    ${actionsList || '<div style="font-size:0.8rem; color:#64748b;">No actions recorded today.</div>'}
                  </div>
                </div>
              </div>
            </div>
          `;
          break;
        }

        case "UPCOMING_TASKS_VIEWER": {
          const tasks = (p.tasks || []).map((t) => `
            <li class="routine-item" style="padding:0.4rem 0.6rem; margin-bottom:0.3rem;">
              <div class="routine-left" style="gap:0.5rem;">
                <span style="font-size:0.9rem;">${t.status === 'completed' ? '✓' : '○'}</span>
                <div>
                  <div style="font-size:0.85rem; font-weight:600;">${escapeHtml(t.title)}</div>
                  <div style="font-size:0.72rem; color:#94a3b8;">${t.scheduled_time || 'Anchor'} • ${escapeHtml(t.recurrence || 'daily')}</div>
                </div>
              </div>
              <div class="routine-right">
                <span class="routine-badge-tag" style="font-size:0.65rem;">${t.status === 'completed' ? 'Audio Verified' : 'Watching'}</span>
              </div>
            </li>
          `).join("");

          echoCardCanvas.innerHTML = `
            <div class="echo-card-inner">
              <div class="echo-card-category">WATCHING AUDIO STREAM</div>
              <h2 class="echo-card-headline" style="font-size:1.15rem; margin-bottom:0.4rem;">
                ${p.total_tasks || 0} Scheduled Peace of Mind Routines
              </h2>
              <ul class="routines-list" style="margin:0.4rem 0 0 0; padding:0; list-style:none; max-height:220px; overflow-y:auto;">
                ${tasks || '<li style="font-size:0.8rem; color:#64748b;">No upcoming routines found.</li>'}
              </ul>
            </div>
          `;
          break;
        }

        default: {
          echoCardCanvas.innerHTML = `
            <div class="echo-card-inner">
              <div class="echo-card-category">ALEXA MULTI-MODAL CARD</div>
              <h2 class="echo-card-headline">${escapeHtml(card.ui_card_type || 'EXAMEN Intelligence')}</h2>
              <pre style="font-size:0.75rem; color:#cbd5e1; background:rgba(0,0,0,0.3); padding:0.5rem; border-radius:6px; overflow:auto;">${escapeHtml(JSON.stringify(card.card_payload, null, 2))}</pre>
            </div>
          `;
        }
      }
    } catch (err) {
      console.error("Failed to render Echo card preview:", err);
      echoCardCanvas.innerHTML = `<div class="echo-card-loading" style="color:#f87171;">Failed to load card preview: ${escapeHtml(err.message)}</div>`;
    }
  }

  function openEchoModal(templateKey) {
    updateEchoClock();
    echoClockInterval = setInterval(updateEchoClock, 10000);
    renderEchoCard(templateKey || activeEchoTemplate);
    modalEchoShow?.classList.remove("hidden");
  }

  function closeEchoModal() {
    modalEchoShow?.classList.add("hidden");
    if (echoClockInterval) {
      clearInterval(echoClockInterval);
      echoClockInterval = null;
    }
  }

  btnOpenEchoModal?.addEventListener("click", () => openEchoModal());
  btnCloseEcho?.addEventListener("click", closeEchoModal);
  modalEchoShow?.addEventListener("click", (e) => {
    if (e.target === modalEchoShow) closeEchoModal();
  });

  echoTabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const tmpl = btn.dataset.template;
      if (tmpl) renderEchoCard(tmpl);
    });
  });

  // Deep linking URL parameter check
  const urlParams = new URLSearchParams(window.location.search);
  const cardParam = urlParams.get("card");
  const modeParam = urlParams.get("mode");
  const contactParam = urlParams.get("contact");

  if (cardParam || modeParam === "ext-app") {
    openEchoModal(cardParam || "DEEP_BRIEFING_VIEWER");
  }
  if (contactParam) {
    setTimeout(() => openDossierModal(contactParam), 500);
  }

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
            } else if (payload.type === "contact_enriched") {
              showToast(`Web dossier enriched for ${payload.data?.name || "contact"}!`, "success");
              refreshAll();
            } else if (payload.type && (payload.type.startsWith("routine_") || payload.type.startsWith("commitment_") || payload.type.startsWith("contact_"))) {
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
