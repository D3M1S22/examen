"use client";

import { useState, useEffect } from "react";
import useSWR from "swr";
import { PlannedTask, VerifiedAction, SocialEntity, BriefingReport } from "@/types/schemas";

import { SystemBar } from "@/components/SystemBar";
import { SystemFooter } from "@/components/SystemFooter";
import { OverviewHub } from "@/components/views/OverviewHub";
import { PeaceOfMind } from "@/components/views/PeaceOfMind";
import { DailyRoutines } from "@/components/views/DailyRoutines";
import { SocialRolodex } from "@/components/views/SocialRolodex";
import { TopicDossiers } from "@/components/views/TopicDossiers";
import { AmbientSimulator } from "@/components/views/AmbientSimulator";

// Use environment variable for API URL or default to empty string (same origin)
const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

const fetcher = (url: string) => fetch(`${API_URL}${url}`).then((res) => res.json());

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState("overview");
  const [currentTime, setCurrentTime] = useState("");
  const [simText, setSimText] = useState("");
  const [simRunning, setSimRunning] = useState(false);
  const [simResult, setSimResult] = useState<any>(null);

  // SWR Hooks for data fetching
  const { data: statusData } = useSWR("/api/status", fetcher, { refreshInterval: 15000 });
  const { data: routinesData, mutate: mutateRoutines } = useSWR<{ tasks: PlannedTask[] }>("/api/routines", fetcher);
  const { data: actionsData } = useSWR<{ actions: VerifiedAction[] }>("/api/actions?limit=50", fetcher);
  const { data: socialData } = useSWR<{ contacts: SocialEntity[] }>("/api/contacts", fetcher);
  const { data: topicsData } = useSWR<{ topics: BriefingReport[] }>("/api/topics?limit=20", fetcher);

  // System clock
  useEffect(() => {
    const timer = setInterval(() => {
      const now = new Date();
      setCurrentTime(`${now.getUTCHours().toString().padStart(2, "0")}:${now.getUTCMinutes().toString().padStart(2, "0")} UTC`);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Simulator
  const runSimulation = async () => {
    if (!simText.trim()) return;
    setSimRunning(true);
    setSimResult(null);
    try {
      const res = await fetch(`${API_URL}/api/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript_chunk: simText }),
      });
      const data = await res.json();
      setSimResult(data);
    } catch (e) {
      console.error(e);
    } finally {
      setSimRunning(false);
    }
  };

  const handleToggleRoutine = async (task: PlannedTask) => {
    // Optimistic update
    const prevTasks = routinesData?.tasks || [];
    const updatedTasks = prevTasks.map(t => t.id === task.id ? { ...t, status: t.status === "completed" ? "pending" : "completed" } : t);
    
    await mutateRoutines({ tasks: updatedTasks as PlannedTask[] }, false);
    
    // API Call
    try {
      await fetch(`${API_URL}/api/routines/${task.id}/toggle`, { method: "POST" });
      mutateRoutines(); // Revalidate
    } catch (err) {
      mutateRoutines({ tasks: prevTasks }, false); // Rollback
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <SystemBar 
        activeTab={activeTab} 
        setActiveTab={setActiveTab} 
        currentTime={currentTime} 
      />

      {/* MAIN CONTENT AREA */}
      <main className="max-w-[1600px] mx-auto px-gutter-desktop pt-8 pb-16">
        {activeTab === "overview" && (
          <OverviewHub 
            routinesData={routinesData} 
            setActiveTab={setActiveTab}
            setSimText={setSimText}
            handleToggleRoutine={handleToggleRoutine}
          />
        )}

        {activeTab === "simulator" && (
          <AmbientSimulator 
            simText={simText}
            setSimText={setSimText}
            simRunning={simRunning}
            runSimulation={runSimulation}
            simResult={simResult}
          />
        )}

        {activeTab === "peace" && (
          <PeaceOfMind actionsData={actionsData} />
        )}

        {activeTab === "routines" && (
          <DailyRoutines 
            routinesData={routinesData} 
            handleToggleRoutine={handleToggleRoutine} 
          />
        )}

        {activeTab === "social" && (
          <SocialRolodex socialData={socialData} />
        )}

        {activeTab === "topics" && (
          <TopicDossiers topicsData={topicsData} />
        )}
      </main>

      <SystemFooter />
    </div>
  );
}
