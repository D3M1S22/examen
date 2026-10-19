"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import useSWR, { useSWRConfig } from "swr";
import {
  PlannedTask,
  VerifiedAction,
  SocialEntity,
  BriefingReport,
  SessionUser,
  EchoNotification,
  EventEngineStatus,
  EventSummary,
  BackfillProgress,
} from "@/types/schemas";
import { EventAction } from "@/components/ui/EventCard";

import { SystemBar } from "@/components/SystemBar";
import { StatusDock } from "@/components/ui/StatusDock";
import { SystemFooter } from "@/components/SystemFooter";
import { OverviewHub } from "@/components/views/OverviewHub";
import { PeaceOfMind } from "@/components/views/PeaceOfMind";
import { DailyRoutines } from "@/components/views/DailyRoutines";
import { SocialRolodex } from "@/components/views/SocialRolodex";
import { TopicDossiers } from "@/components/views/TopicDossiers";
import { AmbientSimulator } from "@/components/views/AmbientSimulator";
import { EchoShowModal } from "@/components/ui/EchoShowModal";
import { LoginModal } from "@/components/ui/LoginModal";
import { BackfillModal } from "@/components/ui/BackfillModal";
import { formatDuration, mergeProgress } from "@/utils/backfill";
import { getApiBaseUrl } from "@/utils/api";
import { AUTH_EXPIRED_EVENT, eraseAccount, fetchSession, installAuthFetch, logout, unlinkBee } from "@/utils/auth";

const fetcher = (url: string) => fetch(`${getApiBaseUrl()}${url}`).then((res) => res.json());

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState("overview");
  const [echoModalInitialTab, setEchoModalInitialTab] = useState("overview");
  const [currentTime, setCurrentTime] = useState("");
  const [simText, setSimText] = useState("");
  const [simRunning, setSimRunning] = useState(false);
  const [simResult, setSimResult] = useState<any>(null);
  const [showGlobalEchoModal, setShowGlobalEchoModal] = useState(false);
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [loginModalConnectBee, setLoginModalConnectBee] = useState(false);
  const [currentUser, setCurrentUser] = useState<SessionUser | null>(null);
  // Multi-user: the dashboard loads data only once the session cookie is verified
  const [sessionChecked, setSessionChecked] = useState(false);
  const [sseConnected, setSseConnected] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [updatedTabs, setUpdatedTabs] = useState<Record<string, number>>({});
  const [echoNotification, setEchoNotification] = useState<EchoNotification | null>(null);
  const echoNotifTimerRef = useRef<NodeJS.Timeout | null>(null);
  const [eventMode, setEventMode] = useState(false);
  const [showBackfillModal, setShowBackfillModal] = useState(false);
  const [backfillProgress, setBackfillProgress] = useState<BackfillProgress | null>(null);
  const { mutate: globalMutate } = useSWRConfig();

  const handleOpenEchoModal = useCallback((tab: string = "overview") => {
    setEchoModalInitialTab(tab);
    setShowGlobalEchoModal(true);
  }, []);

  // Verify the server session on mount; any 401 later brings the sign-in form back
  useEffect(() => {
    installAuthFetch();
    fetchSession()
      .then((user) => setCurrentUser(user))
      .finally(() => setSessionChecked(true));
    const onExpired = () => setCurrentUser(null);
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  }, []);
  const authed = currentUser !== null;

  // SWR Data Fetching
  const { data: statusData, mutate: mutateStatus } = useSWR(authed ? "/api/status" : null, fetcher, { refreshInterval: 10000 });
  const { data: routinesData, mutate: mutateRoutines } = useSWR<{ tasks: PlannedTask[] }>(
    authed ? "/api/routines" : null,
    fetcher
  );
  const { data: actionsData, mutate: mutateActions } = useSWR<{ actions: VerifiedAction[] }>(
    authed ? "/api/actions?limit=50" : null,
    fetcher
  );
  const { data: socialData, mutate: mutateSocial } = useSWR<{ contacts: SocialEntity[] }>(
    authed ? "/api/contacts" : null,
    fetcher
  );
  const { data: topicsData, mutate: mutateTopics } = useSWR<{ topics: BriefingReport[] }>(
    authed ? "/api/topics?limit=20" : null,
    fetcher
  );
  // Deep Topic Event Engine: events (lectures/meetings) and live engine state
  const { data: sessionsData, mutate: mutateSessions } = useSWR<{ sessions: EventSummary[] }>(
    authed ? "/api/sessions?events_only=true&limit=20" : null,
    fetcher,
    { refreshInterval: 15000 }
  );
  const { data: engineStatus, mutate: mutateEngine } = useSWR<EventEngineStatus>(
    authed ? "/api/event-engine/status" : null,
    fetcher,
    { refreshInterval: 5000 }
  );

  const refreshEvents = useCallback(() => {
    mutateSessions();
    mutateEngine();
    mutateTopics();
    // Event detail cards (/api/sessions/{id}) revalidate too
    globalMutate((key) => typeof key === "string" && key.startsWith("/api/sessions/"));
  }, [mutateSessions, mutateEngine, mutateTopics, globalMutate]);

  const showToast = useCallback((msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3500);
  }, []);

  const markTabUpdated = useCallback((tabId: string) => {
    setUpdatedTabs((prev) => ({
      ...prev,
      [tabId]: (prev[tabId] || 0) + 1,
    }));
  }, []);

  const handleClearTabBadge = useCallback((tabId: string) => {
    setUpdatedTabs((prev) => {
      if (!prev[tabId]) return prev;
      const next = { ...prev };
      delete next[tabId];
      return next;
    });
  }, []);

  const notifyEcho = useCallback((notif: Omit<EchoNotification, "id" | "timestamp">) => {
    const newNotif: EchoNotification = {
      ...notif,
      id: `notif-${Date.now()}`,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };
    setEchoNotification(newNotif);

    if (echoNotifTimerRef.current) clearTimeout(echoNotifTimerRef.current);
    echoNotifTimerRef.current = setTimeout(() => {
      setEchoNotification(null);
    }, 10000);
  }, []);

  // Automatically clear active tab badge when viewed
  useEffect(() => {
    handleClearTabBadge(activeTab);
  }, [activeTab, handleClearTabBadge]);

  // Deep link: ?tab=topics | simulator | social | routines | peace
  useEffect(() => {
    if (typeof window === "undefined") return;
    const tab = new URLSearchParams(window.location.search).get("tab");
    if (tab && ["overview", "peace", "routines", "social", "topics", "simulator"].includes(tab)) setActiveTab(tab);
  }, []);

  // System Clock
  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setCurrentTime(
        `${now.getUTCHours().toString().padStart(2, "0")}:${now
          .getUTCMinutes()
          .toString()
          .padStart(2, "0")} UTC`
      );
    };
    updateTime();
    const timer = setInterval(updateTime, 1000);
    return () => clearInterval(timer);
  }, []);

  // Server-Sent Events (SSE) live connection to /api/events
  useEffect(() => {
    if (typeof window === "undefined" || !("EventSource" in window) || !authed) return;
    try {
      const baseUrl = getApiBaseUrl();
      // The session cookie authenticates the stream (EventSource cannot send custom headers)
      const es = new EventSource(`${baseUrl}/api/events`, { withCredentials: true });

      es.onopen = () => {
        setSseConnected(true);
      };

      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          const eventType = (data.type || data.event || "").toLowerCase();
          const eventPayload = data.data || {};

          // Revalidate status on any backend change
          mutateStatus();

          // History backfill: one progress indicator and one completion toast per run (no per-entity toasts)
          if (eventType.startsWith("backfill_")) {
            if (eventPayload.run_id) {
              setBackfillProgress((prev) => mergeProgress(prev, eventPayload as BackfillProgress));
            }
            if (eventType === "backfill_completed") {
              const c = eventPayload.counters || {};
              mutateActions();
              mutateRoutines();
              mutateSocial();
              refreshEvents();
              markTabUpdated("overview");
              showToast(
                eventPayload.status === "cancelled"
                  ? "⏪ History analysis stopped"
                  : `⏪ History recovered: ${c.actions || 0} actions · ${c.contacts || 0} contacts · ${c.tasks || 0} tasks · ${c.events || 0} events`
              );
            } else if (eventType === "backfill_failed") {
              showToast(`⏪ History analysis failed: ${eventPayload.error || "unknown error"}`);
            }
            return;
          }
          if (eventType === "coverage_gap_detected") {
            showToast(`⏪ Offline gap detected (${formatDuration(eventPayload.seconds)}): it will be recovered automatically`);
            return;
          }

          // Intelligent routing of SSE cache invalidation and UI notification triggers
          if (eventType.includes("action")) {
            mutateActions();
            markTabUpdated("peace");
            markTabUpdated("overview");
            showToast("⚡ Acoustic action verified and recorded into ledger");
            notifyEcho({
              title: "Acoustic Action Verified",
              message:
                eventPayload.raw_statement ||
                eventPayload.action_type ||
                "Acoustic corroboration successfully registered.",
              category: "action",
              targetTab: "peace",
            });
          }
          if (eventType.includes("routine") || eventType.includes("task")) {
            mutateRoutines();
            markTabUpdated("routines");
            markTabUpdated("overview");
            showToast(`📋 Monitored routine updated: ${eventPayload.title || "Checklist modified"}`);
            notifyEcho({
              title: "Monitored Routine Updated",
              message: eventPayload.title
                ? `Routine '${eventPayload.title}' state altered.`
                : "Planned routine checklist status changed.",
              category: "routine",
              targetTab: "routines",
            });
          }
          if (eventType.includes("contact") || eventType.includes("commitment") || eventType.includes("social")) {
            mutateSocial();
            markTabUpdated("social");
            markTabUpdated("overview");
            showToast(
              `👥 Social intelligence updated: ${
                eventPayload.person_name || eventPayload.contact_name || "Profile indexed"
              }`
            );
            notifyEcho({
              title: "Social Intelligence Corroborated",
              message:
                eventPayload.person_name || eventPayload.contact_name
                  ? `Contact record for ${eventPayload.person_name || eventPayload.contact_name} updated.`
                  : "Bilateral commitment status updated.",
              category: "social",
              targetTab: "social",
            });
          }
          if (eventType.includes("topic") || eventType.includes("briefing")) {
            mutateTopics();
            markTabUpdated("topics");
            markTabUpdated("overview");
            showToast(`📚 Topic dossier compiled: ${eventPayload.topic_title || "Research note"}`);
            notifyEcho({
              title: "Topic Dossier Compiled",
              message: eventPayload.topic_title
                ? `Autonomous briefing completed for '${eventPayload.topic_title}'.`
                : "Technical briefing dossier synthesized with web citations.",
              category: "topic",
              targetTab: "topics",
            });
          }
          if (eventType.startsWith("event_") || eventType.startsWith("segment_")) {
            refreshEvents();
            markTabUpdated("topics");
            markTabUpdated("overview");
            notifyEcho({
              title: "Lecture / Event Updated",
              message: "Deep topic event timeline refreshed.",
              category: "topic",
              targetTab: "topics",
            });
          }
          if (eventType.includes("pipeline") || eventType.includes("session")) {
            mutateActions();
            mutateRoutines();
            mutateSocial();
            mutateTopics();
            mutateStatus();
            refreshEvents();
            markTabUpdated("overview");
            markTabUpdated("simulator");
            showToast("⚡ Real-time ambient speech processed by Bedrock AgentCore");
            notifyEcho({
              title: "Ambient Ingestion Completed",
              message: "Audio stream processed across all domain extractors.",
              category: "system",
              targetTab: "overview",
            });
          }
          if (
            eventType.includes("user_logged_in") ||
            eventType.includes("user_logged_out") ||
            eventType.includes("bee_disconnected")
          ) {
            mutateStatus();
          }
        } catch {
          // heartbeat or raw text
        }
      };

      es.onerror = () => {
        setSseConnected(false);
      };

      return () => {
        es.close();
      };
    } catch (err) {
      console.warn("SSE connection error:", err);
    }
  }, [authed, mutateActions, mutateRoutines, mutateSocial, mutateTopics, mutateStatus, refreshEvents, markTabUpdated, notifyEcho, showToast]);

  // Auth & GDPR Handlers
  const handleLoginSuccess = (user: SessionUser) => {
    setCurrentUser(user);
    showToast(`Welcome, ${user.handle}!`);
    mutateStatus();
    notifyEcho({
      title: "Signed in",
      message: `Signed in as ${user.handle}. Only your own data is shown.`,
      category: "system",
      targetTab: "overview",
    });
  };

  const handleLogout = async () => {
    await logout();
    setCurrentUser(null);
    showToast("Signed out. Your Bee keeps streaming to your account.");
  };

  const handlePurgeData = async () => {
    const password = window.prompt("GDPR Art. 17: enter your password to permanently erase your account and all its data");
    if (!password) return;
    try {
      await eraseAccount(password);
      setCurrentUser(null);
      showToast("Your account and all its data were permanently erased (GDPR Art. 17).");
    } catch (err: any) {
      showToast(`Erasure failed: ${err?.message || err}`);
    }
  };

  const handleDisconnectBee = async () => {
    try {
      await unlinkBee();
      setCurrentUser(await fetchSession());
      showToast("Your Bee account was disconnected. Your data is kept.");
    } catch (err: any) {
      showToast(`Disconnect failed: ${err?.message || err}`);
    }
    mutateStatus();
  };

  const handleOpenBeePairing = () => {
    setLoginModalConnectBee(true);
    setShowLoginModal(true);
  };

  // Simulator Execution
  const runSimulation = async () => {
    if (!simText.trim()) return;
    setSimRunning(true);
    setSimResult(null);
    try {
      const baseUrl = getApiBaseUrl();
      const res = await fetch(`${baseUrl}/api/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript_chunk: simText, event_mode: eventMode }),
      });
      const data = await res.json();
      setSimResult(data);
      if (eventMode) refreshEvents();
      // Revalidate all data streams
      mutateRoutines();
      mutateActions();
      mutateSocial();
      mutateTopics();
      mutateStatus();
      markTabUpdated("simulator");
      markTabUpdated("overview");
      showToast("Simulation pipeline executed successfully!");
      notifyEcho({
        title: "Simulation Pipeline Ingested",
        message: "Spoken transcript parsed through Bedrock AgentCore runtime.",
        category: "system",
        targetTab: "overview",
      });
    } catch (e: any) {
      console.error(e);
      showToast("Simulation failed: " + (e?.message || "network error"));
    } finally {
      setSimRunning(false);
    }
  };

  // Scenario player: one utterance with its recorded gatekeeper labels (event mode)
  const simulateUtterance = async (text: string, categories?: string[]) => {
    const res = await fetch(`${getApiBaseUrl()}/api/simulate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transcript_chunk: text, event_mode: true, categories }),
    });
    const data = await res.json();
    setSimResult(data);
    return data;
  };

  // Simulator virtual clock (event engine timers)
  const handleTick = async (seconds: number, reset = false) => {
    const res = await fetch(`${getApiBaseUrl()}/api/simulate/tick`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(reset ? { reset: true } : { seconds }),
    });
    const data = await res.json();
    refreshEvents();
    return data;
  };

  // Event card actions (pause = synthesize now, resume, conclude, split, merge)
  const handleEventAction = async (action: EventAction, ev: EventSummary, extra?: Record<string, any>) => {
    const baseUrl = getApiBaseUrl();
    let url = `${baseUrl}/api/sessions/${ev.session_id}/${action}`;
    let body: Record<string, any> = {};
    if (action === "split") body = { at_time: extra?.at_time };
    if (action === "merge") {
      url = `${baseUrl}/api/sessions/merge`;
      body = { session_ids: [extra?.with, ev.session_id] };
    }
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok || data.success === false) throw new Error(data.error || `HTTP ${res.status}`);
      const labels: Record<EventAction, string> = {
        pause: "Segment closed — synthesis started",
        resume: "Event resumed",
        conclude: "Event concluded — final synthesis scheduled",
        split: "Event split — both parts will be re-synthesized",
        merge: "Events merged — final briefing will be regenerated",
      };
      showToast(labels[action]);
    } catch (err: any) {
      showToast(`Event ${action} failed: ${err.message}`);
    } finally {
      refreshEvents();
    }
  };

  // Toggle routine status
  const handleToggleRoutine = async (task: PlannedTask) => {
    const prevTasks = routinesData?.tasks || [];
    const newStatus = task.status === "completed" ? "pending" : "completed";
    const updatedTasks = prevTasks.map((t) =>
      t.id === task.id ? { ...t, status: newStatus as any } : t
    );

    // Optimistic update
    await mutateRoutines({ tasks: updatedTasks as PlannedTask[] }, false);

    try {
      const baseUrl = getApiBaseUrl();
      await fetch(`${baseUrl}/api/routines/${task.id}/toggle`, { method: "POST" });
      mutateRoutines();
      mutateStatus();
      markTabUpdated("routines");
      markTabUpdated("overview");
      showToast(`Routine marked ${newStatus.toUpperCase()}`);
      notifyEcho({
        title: "Routine Check Updated",
        message: `Routine '${task.title}' marked ${newStatus.toUpperCase()}`,
        category: "routine",
        targetTab: "routines",
      });
    } catch (err) {
      mutateRoutines({ tasks: prevTasks }, false);
      showToast("Failed to update routine status.");
    }
  };

  // Add routine
  const handleAddRoutine = async (
    title: string,
    domain: string,
    scheduled_time: string,
    recurrence: string = "daily"
  ) => {
    try {
      const baseUrl = getApiBaseUrl();
      const res = await fetch(`${baseUrl}/api/routines`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, domain, scheduled_time, recurrence }),
      });
      if (!res.ok) throw new Error("Failed to create routine");
      await mutateRoutines();
      await mutateStatus();
      markTabUpdated("routines");
      markTabUpdated("overview");
      showToast("New monitored routine activated!");
      notifyEcho({
        title: "New Routine Activated",
        message: `Monitored task '${title}' registered for ${scheduled_time}`,
        category: "routine",
        targetTab: "routines",
      });
    } catch (err: any) {
      console.error(err);
      showToast("Error creating routine: " + err.message);
      throw err;
    }
  };

  // Delete routine
  const handleDeleteRoutine = async (taskId: string) => {
    try {
      const baseUrl = getApiBaseUrl();
      const res = await fetch(`${baseUrl}/api/routines/${taskId}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("Failed to delete routine");
      await mutateRoutines();
      await mutateStatus();
      markTabUpdated("routines");
      markTabUpdated("overview");
      showToast("Routine deleted successfully.");
      notifyEcho({
        title: "Routine Deleted",
        message: "Monitored routine removed from schedule.",
        category: "routine",
        targetTab: "routines",
      });
    } catch (err: any) {
      console.error(err);
      showToast("Error deleting routine.");
    }
  };

  // Add quick peace of mind action
  const handleAddAction = async (statement: string) => {
    try {
      const baseUrl = getApiBaseUrl();
      const res = await fetch(`${baseUrl}/api/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript_chunk: statement }),
      });
      if (!res.ok) throw new Error("Failed to verify action");
      await mutateActions();
      await mutateRoutines();
      await mutateStatus();
      markTabUpdated("peace");
      markTabUpdated("overview");
      showToast("Action verified & ingested into acoustic ledger!");
      notifyEcho({
        title: "Acoustic Action Corroborated",
        message: statement,
        category: "action",
        targetTab: "peace",
      });
    } catch (err: any) {
      console.error(err);
      showToast("Error recording action.");
      throw err;
    }
  };

  // Trigger Live AI Web Profiler for contact
  const handleEnrichContact = async (contactId: string) => {
    try {
      const baseUrl = getApiBaseUrl();
      const res = await fetch(`${baseUrl}/api/contacts/${contactId}/enrich`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Enrichment failed");
      await mutateSocial();
      await mutateStatus();
      markTabUpdated("social");
      markTabUpdated("overview");
      showToast("Executive AI web enrichment completed!");
      notifyEcho({
        title: "Executive Profile AI Enriched",
        message: "Corroborated web profile compiled with source citations.",
        category: "social",
        targetTab: "social",
      });
    } catch (err: any) {
      console.error(err);
      showToast("Enrichment error: " + err.message);
      throw err;
    }
  };

  // Toggle commitment fulfillment
  const handleToggleCommitment = async (commitmentId: string, action: "fulfill" | "cancel") => {
    try {
      const baseUrl = getApiBaseUrl();
      const res = await fetch(`${baseUrl}/api/commitments/${commitmentId}/${action}`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(`Failed to ${action} commitment`);
      await mutateSocial();
      await mutateStatus();
      markTabUpdated("social");
      markTabUpdated("overview");
      showToast(`Commitment marked ${action === "fulfill" ? "FULFILLED" : "CANCELLED"}!`);
      notifyEcho({
        title: "Commitment State Changed",
        message: `Commitment marked ${action === "fulfill" ? "FULFILLED" : "CANCELLED"}`,
        category: "social",
        targetTab: "social",
      });
    } catch (err: any) {
      console.error(err);
      showToast(`Error updating commitment: ${err.message}`);
    }
  };

  return (
    <div className="min-h-screen bg-background relative flex flex-col justify-between">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-[10000] px-5 py-3 rounded-xl bg-zinc-900 border border-emerald-500/50 text-emerald-300 font-mono text-[11px] tracking-wider shadow-2xl animate-in slide-in-from-bottom-5 duration-200 flex items-center gap-2">
          <span>⚡</span>
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Global Echo Show Multimodal Modal with Specular Tabs and Login */}
      <EchoShowModal
        isOpen={showGlobalEchoModal}
        onClose={() => setShowGlobalEchoModal(false)}
        initialTab={echoModalInitialTab}
        statusData={statusData}
        routinesData={routinesData}
        actionsData={actionsData}
        socialData={socialData}
        topicsData={topicsData}
        sessionsData={sessionsData}
        engineStatus={engineStatus}
        currentUser={currentUser}
        onOpenLoginModal={() => {
          setLoginModalConnectBee(false);
          setShowLoginModal(true);
        }}
        onLogout={handleLogout}
        onDisconnectBee={handleDisconnectBee}
        onToggleRoutine={handleToggleRoutine}
        handleAddRoutine={handleAddRoutine}
        handleDeleteRoutine={handleDeleteRoutine}
        handleAddAction={handleAddAction}
        handleEnrichContact={handleEnrichContact}
        handleToggleCommitment={handleToggleCommitment}
        simText={simText}
        setSimText={setSimText}
        simRunning={simRunning}
        runSimulation={runSimulation}
        simResult={simResult}
        echoNotification={echoNotification}
        onDismissNotification={() => setEchoNotification(null)}
        updatedTabs={updatedTabs}
        onClearTabBadge={handleClearTabBadge}
      />

      {/* GDPR-Compliant Login & Bee Pairing Modal */}
      <LoginModal
        isOpen={showLoginModal || (sessionChecked && !currentUser)}
        mandatory={!currentUser}
        onClose={() => setShowLoginModal(false)}
        onLoginSuccess={(user) => {
          handleLoginSuccess(user);
          setShowLoginModal(false);
        }}
        currentUser={currentUser}
        initialConnectBee={loginModalConnectBee}
        onLogout={handleLogout}
        onSessionChanged={(user) => {
          setCurrentUser(user);
          mutateStatus();
        }}
      />

      {/* Left-Side Auto-Hiding Floating Status Dock (MacBook Pro Style) */}
      <StatusDock
        sseConnected={sseConnected}
        statusData={statusData}
        onOpenEchoModal={() => handleOpenEchoModal("overview")}
        backfillProgress={backfillProgress}
        onOpenBackfill={() => setShowBackfillModal(true)}
      />

      {/* History Sync: analyse a past period from Bee history */}
      <BackfillModal
        isOpen={showBackfillModal}
        onClose={() => setShowBackfillModal(false)}
        history={statusData?.telemetry}
        liveProgress={backfillProgress}
        onRunQueued={() => {
          mutateStatus();
          showToast("⏪ History analysis queued");
        }}
      />

      <div>
        <SystemBar
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          currentTime={currentTime}
          onOpenEchoModal={() => handleOpenEchoModal(activeTab)}
          sseConnected={sseConnected}
          statusData={statusData}
          currentUser={currentUser}
          onOpenLoginModal={() => {
            setLoginModalConnectBee(false);
            setShowLoginModal(true);
          }}
          onLogout={handleLogout}
          onPurgeData={handlePurgeData}
          onOpenBeePairing={handleOpenBeePairing}
          onDisconnectBee={handleDisconnectBee}
          updatedTabs={updatedTabs}
          onClearTabBadge={handleClearTabBadge}
        />

        {/* MAIN CONTENT AREA - Symmetric, clean padding without dock offset */}
        <main className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 xl:px-gutter-desktop pt-8 pb-16 transition-all duration-300">
          {activeTab === "overview" && (
            <OverviewHub
              statusData={statusData}
              routinesData={routinesData}
              actionsData={actionsData}
              socialData={socialData}
              topicsData={topicsData}
              engineStatus={engineStatus}
              setActiveTab={setActiveTab}
              setSimText={setSimText}
              handleToggleRoutine={handleToggleRoutine}
              onOpenEchoModal={handleOpenEchoModal}
              backfillProgress={backfillProgress}
              onOpenBackfill={() => setShowBackfillModal(true)}
            />
          )}

          {activeTab === "peace" && (
            <PeaceOfMind
              actionsData={actionsData}
              statusData={statusData}
              onAddAction={handleAddAction}
            />
          )}

          {activeTab === "routines" && (
            <DailyRoutines
              routinesData={routinesData}
              statusData={statusData}
              handleToggleRoutine={handleToggleRoutine}
              handleAddRoutine={handleAddRoutine}
              handleDeleteRoutine={handleDeleteRoutine}
            />
          )}

          {activeTab === "social" && (
            <SocialRolodex
              socialData={socialData}
              statusData={statusData}
              onEnrichContact={handleEnrichContact}
              onToggleCommitment={handleToggleCommitment}
            />
          )}

          {activeTab === "topics" && (
            <TopicDossiers
              topicsData={topicsData}
              statusData={statusData}
              sessionsData={sessionsData}
              engineStatus={engineStatus}
              onEventAction={handleEventAction}
            />
          )}

          {activeTab === "simulator" && (
            <AmbientSimulator
              simText={simText}
              setSimText={setSimText}
              simRunning={simRunning}
              runSimulation={runSimulation}
              simResult={simResult}
              statusData={statusData}
              eventMode={eventMode}
              setEventMode={setEventMode}
              engineStatus={engineStatus}
              onTick={handleTick}
              simulateUtterance={simulateUtterance}
              onOpenEvents={() => setActiveTab("topics")}
            />
          )}
        </main>
      </div>

      <SystemFooter />
    </div>
  );
}
