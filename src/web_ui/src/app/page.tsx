"use client";

import { useState, useEffect, useCallback } from "react";
import useSWR, { useSWRConfig } from "swr";
import {
  PlannedTask,
  VerifiedAction,
  SocialEntity,
  BriefingReport,
  EventEngineStatus,
  EventSummary,
} from "@/types/schemas";
import { EventAction } from "@/components/ui/EventCard";

import { SystemBar } from "@/components/SystemBar";
import { SystemFooter } from "@/components/SystemFooter";
import { OverviewHub } from "@/components/views/OverviewHub";
import { PeaceOfMind } from "@/components/views/PeaceOfMind";
import { DailyRoutines } from "@/components/views/DailyRoutines";
import { SocialRolodex } from "@/components/views/SocialRolodex";
import { TopicDossiers } from "@/components/views/TopicDossiers";
import { AmbientSimulator } from "@/components/views/AmbientSimulator";
import { EchoShowModal } from "@/components/ui/EchoShowModal";
import { getApiBaseUrl } from "@/utils/api";

const fetcher = (url: string) => fetch(`${getApiBaseUrl()}${url}`).then((res) => res.json());

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState("overview");
  const [currentTime, setCurrentTime] = useState("");
  const [simText, setSimText] = useState("");
  const [simRunning, setSimRunning] = useState(false);
  const [simResult, setSimResult] = useState<any>(null);
  const [showGlobalEchoModal, setShowGlobalEchoModal] = useState(false);
  const [sseConnected, setSseConnected] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [eventMode, setEventMode] = useState(false);
  const { mutate: globalMutate } = useSWRConfig();

  // SWR Data Fetching
  const { data: statusData, mutate: mutateStatus } = useSWR("/api/status", fetcher, { refreshInterval: 10000 });
  const { data: routinesData, mutate: mutateRoutines } = useSWR<{ tasks: PlannedTask[] }>(
    "/api/routines",
    fetcher
  );
  const { data: actionsData, mutate: mutateActions } = useSWR<{ actions: VerifiedAction[] }>(
    "/api/actions?limit=50",
    fetcher
  );
  const { data: socialData, mutate: mutateSocial } = useSWR<{ contacts: SocialEntity[] }>(
    "/api/contacts",
    fetcher
  );
  const { data: topicsData, mutate: mutateTopics } = useSWR<{ topics: BriefingReport[] }>(
    "/api/topics?limit=20",
    fetcher
  );
  // Deep Topic Event Engine: events (lectures/meetings) and live engine state
  const { data: sessionsData, mutate: mutateSessions } = useSWR<{ sessions: EventSummary[] }>(
    "/api/sessions?events_only=true&limit=20",
    fetcher,
    { refreshInterval: 15000 }
  );
  const { data: engineStatus, mutate: mutateEngine } = useSWR<EventEngineStatus>(
    "/api/event-engine/status",
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
    if (typeof window === "undefined" || !("EventSource" in window)) return;
    try {
      const baseUrl = getApiBaseUrl();
      const es = new EventSource(`${baseUrl}/api/events`);

      es.onopen = () => {
        setSseConnected(true);
      };

      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          const eventType = (data.type || data.event || "").toLowerCase();

          // Revalidate status on any backend change
          mutateStatus();

          // Intelligent routing of SSE cache invalidation
          if (eventType.includes("action")) mutateActions();
          if (eventType.includes("routine") || eventType.includes("task")) mutateRoutines();
          if (eventType.includes("contact") || eventType.includes("commitment") || eventType.includes("social")) mutateSocial();
          if (eventType.includes("topic") || eventType.includes("briefing")) mutateTopics();
          if (eventType.startsWith("event_") || eventType.startsWith("segment_")) refreshEvents();
          if (eventType.includes("pipeline") || eventType.includes("session")) {
            mutateActions();
            mutateRoutines();
            mutateSocial();
            mutateTopics();
            mutateStatus();
            refreshEvents();
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
  }, [mutateActions, mutateRoutines, mutateSocial, mutateTopics, mutateStatus, refreshEvents]);

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
      showToast("Simulation pipeline executed successfully!");
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
      showToast(`Routine marked ${newStatus.toUpperCase()}`);
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
      showToast("New monitored routine activated!");
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
      showToast("Routine deleted successfully.");
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
      showToast("Action verified & ingested into acoustic ledger!");
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
      showToast("Executive AI web enrichment completed!");
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
      showToast(`Commitment marked ${action === "fulfill" ? "FULFILLED" : "CANCELLED"}!`);
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

      {/* Global Echo Show Multimodal Modal */}
      <EchoShowModal
        isOpen={showGlobalEchoModal}
        onClose={() => setShowGlobalEchoModal(false)}
      />

      <div>
        <SystemBar
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          currentTime={currentTime}
          onOpenEchoModal={() => setShowGlobalEchoModal(true)}
          sseConnected={sseConnected}
          statusData={statusData}
        />

        {/* MAIN CONTENT AREA */}
        <main className="max-w-[1600px] mx-auto px-gutter-desktop pt-8 pb-16">
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
