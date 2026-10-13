"use client";

import { useState, useEffect, useCallback } from "react";
import useSWR from "swr";
import { PlannedTask, VerifiedAction, SocialEntity, BriefingReport } from "@/types/schemas";

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

  const showToast = useCallback((msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3500);
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
          if (eventType.includes("pipeline") || eventType.includes("session")) {
            mutateActions();
            mutateRoutines();
            mutateSocial();
            mutateTopics();
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
  }, [mutateActions, mutateRoutines, mutateSocial, mutateTopics, mutateStatus]);

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
        body: JSON.stringify({ transcript_chunk: simText }),
      });
      const data = await res.json();
      setSimResult(data);
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

      {/* Left-Side Floating Status Dock (MacBook Pro Style) */}
      <StatusDock
        sseConnected={sseConnected}
        statusData={statusData}
        onOpenEchoModal={() => setShowGlobalEchoModal(true)}
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
        <main className="max-w-[1600px] mx-auto px-gutter-desktop pl-16 sm:pl-20 2xl:pl-gutter-desktop pt-8 pb-16">
          {activeTab === "overview" && (
            <OverviewHub
              statusData={statusData}
              routinesData={routinesData}
              actionsData={actionsData}
              socialData={socialData}
              topicsData={topicsData}
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
            <TopicDossiers topicsData={topicsData} statusData={statusData} />
          )}

          {activeTab === "simulator" && (
            <AmbientSimulator
              simText={simText}
              setSimText={setSimText}
              simRunning={simRunning}
              runSimulation={runSimulation}
              simResult={simResult}
              statusData={statusData}
            />
          )}
        </main>
      </div>

      <SystemFooter />
    </div>
  );
}
