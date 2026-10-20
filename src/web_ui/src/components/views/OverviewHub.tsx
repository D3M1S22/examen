import React from "react";
import {
  PlannedTask,
  VerifiedAction,
  SocialEntity,
  BriefingReport,
  EventEngineStatus,
  BackfillProgress,
  CoverageResponse,
  HistoryTelemetry,
} from "@/types/schemas";
import useSWR from "swr";
import { StatusBadge, DomainBadge } from "../ui/StatusBadge";
import { RecoveredBadge } from "../ui/RecoveredBadge";
import { BackfillStopButton } from "../ui/BackfillStopButton";
import { speakAlexaReassurance } from "@/utils/audioEffects";
import { getApiBaseUrl } from "@/utils/api";
import { BUCKET_CLASS, bucketTone, formatDuration, formatRange, historyBadge, isTerminal } from "@/utils/backfill";

const coverageFetcher = (url: string) => fetch(`${getApiBaseUrl()}${url}`).then((res) => res.json());

interface OverviewHubProps {
  statusData?: any;
  routinesData: { tasks: PlannedTask[] } | undefined;
  actionsData: { actions: VerifiedAction[] } | undefined;
  socialData: { contacts: SocialEntity[] } | undefined;
  topicsData: { topics: BriefingReport[] } | undefined;
  engineStatus?: EventEngineStatus;
  setActiveTab: (tab: string) => void;
  setSimText: (text: string) => void;
  handleToggleRoutine: (task: PlannedTask) => void;
  onOpenEchoModal?: (tab?: string) => void;
  backfillProgress?: BackfillProgress | null;
  onOpenBackfill?: () => void;
}

export function OverviewHub({
  statusData,
  routinesData,
  actionsData,
  socialData,
  topicsData,
  engineStatus,
  setActiveTab,
  setSimText,
  handleToggleRoutine,
  onOpenEchoModal,
  backfillProgress,
  onOpenBackfill,
}: OverviewHubProps) {
  const liveEvent = engineStatus?.active_event || null;
  const history: HistoryTelemetry | undefined = statusData?.telemetry;
  const historyState = historyBadge(history, backfillProgress);
  const historyRunId =
    (backfillProgress && !isTerminal(backfillProgress.status) ? backfillProgress.run_id : null) ||
    history?.backfill?.active_run?.run_id ||
    null;
  // 7-day coverage strip (one bucket per day), refreshed with the status poll
  const { data: weekCoverage } = useSWR<CoverageResponse>(
    history?.backfill?.enabled ? "/api/backfill/coverage?bucket=day" : null,
    coverageFetcher,
    { refreshInterval: 60000 }
  );
  const tasks = routinesData?.tasks || [];
  const actions = actionsData?.actions || [];
  const contacts = socialData?.contacts || [];
  const topics = topicsData?.topics || [];

  const completedTasks = statusData?.stats?.planned_tasks_completed ?? tasks.filter((t) => t.status === "completed").length;
  const pendingTasks = statusData?.stats?.planned_tasks_pending ?? tasks.filter((t) => t.status !== "completed").length;
  const totalActionsCount = statusData?.stats?.total_actions ?? actions.length;
  const totalContactsCount = statusData?.stats?.total_contacts ?? contacts.length;
  const totalTopicsCount = statusData?.stats?.total_topics ?? topics.length;

  const handleAlexaVoiceQuery = () => {
    const text = `EXAMEN Ambient Status: Domestic posture is all clear. You have ${totalActionsCount} verified acoustic actions, ${completedTasks} of ${tasks.length} routines completed, and ${totalContactsCount} social contacts indexed.`;
    speakAlexaReassurance(text);
    onOpenEchoModal?.("peace");
  };

  return (
    <div className="space-y-space-xl animate-in fade-in max-w-[1400px] mx-auto">

      {/* Top Status Banner */}
      <div className="card-elevated p-space-xl flex flex-col md:flex-row md:items-center justify-between gap-space-lg bg-surface-container-low border-surface-container-highest rounded-2xl">
        <div className="flex flex-col lg:flex-row items-start lg:items-center gap-space-xl flex-1">
          <div className="flex items-center gap-4 lg:border-r border-surface-container-highest lg:pr-space-xl">
            <div className="w-8 h-8 rounded-full border-4 border-emerald-400 flex items-center justify-center shrink-0 shadow-lg shadow-emerald-950/60">
              <div className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping"></div>
            </div>
            <div>
              <div className="font-mono text-[9px] text-emerald-400 tracking-[0.2em] uppercase mb-1 font-bold">
                DOMESTIC POSTURE // ALL CLEAR
              </div>
              <div className="font-serif text-[28px] text-primary leading-none">
                All Anchors Calibrated
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-y-2 gap-x-6 text-[10px] font-mono tracking-widest text-secondary uppercase py-2">
            <div className="flex items-center gap-1.5">
              <span className="text-emerald-400 font-bold">•</span>
              <span>{pendingTasks} PENDING CHECKS</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-emerald-400 font-bold">•</span>
              <span>{actions.length} VERIFIED ANCHORS</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-amber-400 font-bold">•</span>
              <span>{contacts.length} SOCIAL CONTACTS</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-cyan-400 font-bold">•</span>
              <span>{topics.length} DOSSIERS COMPILED</span>
            </div>
          </div>
        </div>

        {/* Global Action Buttons */}
        <div className="flex items-center gap-3 shrink-0">
          <button
            onClick={handleAlexaVoiceQuery}
            className="px-5 py-3 rounded-xl border border-cyan-500/40 bg-cyan-950/30 hover:bg-cyan-950/60 text-cyan-300 font-mono text-[10px] font-bold tracking-widest uppercase flex items-center gap-2.5 transition-all shadow-md"
            title="Trigger Alexa Ext-App voice report & display"
          >
            <span>🎙️</span>
            <span>ALEXA VOICE QUERY</span>
          </button>

          <button
            onClick={() => setActiveTab("simulator")}
            className="px-5 py-3 rounded-xl bg-primary hover:bg-surface-tint text-background font-mono text-[10px] font-bold tracking-widest uppercase flex items-center gap-2.5 transition-all shadow-md"
          >
            <span>▶</span>
            <span>RUN SIMULATOR</span>
          </button>
        </div>
      </div>

      {/* Live lecture / meeting banner (Deep Topic Event Engine) */}
      {liveEvent && (
        <div
          onClick={() => setActiveTab("topics")}
          className={`card-elevated px-space-xl py-4 rounded-2xl border cursor-pointer flex flex-col md:flex-row md:items-center justify-between gap-3 transition-colors ${
            liveEvent.status === "active"
              ? "bg-emerald-950/20 border-emerald-500/40 hover:border-emerald-400"
              : "bg-amber-950/20 border-amber-500/40 hover:border-amber-400"
          }`}
        >
          <div className="flex items-center gap-4 min-w-0">
            <span className={`w-3 h-3 rounded-full shrink-0 ${liveEvent.status === "active" ? "bg-emerald-400 animate-pulse" : "bg-amber-400"}`} />
            <div className="min-w-0">
              <div className={`font-mono text-[9px] tracking-[0.2em] uppercase font-bold ${liveEvent.status === "active" ? "text-emerald-300" : "text-amber-300"}`}>
                {liveEvent.status === "active" ? "LIVE EVENT // RECORDING" : "LIVE EVENT // PAUSED"}
              </div>
              <div className="font-serif text-[22px] text-primary truncate">
                {liveEvent.title?.startsWith("Ongoing session") ? "Lecture / meeting in progress" : liveEvent.title}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-4 font-mono text-[9px] text-secondary tracking-widest uppercase shrink-0">
            <span>{liveEvent.segments} PART(S)</span>
            {liveEvent.top_terms?.length > 0 && <span className="hidden lg:inline">{liveEvent.top_terms.slice(0, 4).join(" · ")}</span>}
            <span className="text-primary">OPEN TIMELINE →</span>
          </div>
        </div>
      )}

      {/* History Sync: coverage gaps & Bee history backfill */}
      {history?.backfill?.enabled && (
        <div className="card-elevated px-space-xl py-4 rounded-2xl border bg-surface-container-low border-surface-container-highest flex flex-col lg:flex-row lg:items-center gap-4">
          <div className="flex items-center gap-4 min-w-0 lg:w-[34%]">
            <span
              className={`w-3 h-3 rounded-full shrink-0 ${
                historyState.tone === "running"
                  ? "bg-sky-400 animate-pulse"
                  : historyState.tone === "gap"
                  ? "bg-amber-400"
                  : "bg-emerald-400"
              }`}
            />
            <div className="min-w-0">
              <div className="font-mono text-[9px] tracking-[0.2em] uppercase font-bold text-sky-300">
                HISTORY SYNC // {historyState.label}
              </div>
              <div className="font-sans text-body-sm text-secondary truncate">
                {historyState.tone === "running" && backfillProgress
                  ? `Recovering ${formatRange(backfillProgress.window_from, backfillProgress.window_to)}`
                  : history.coverage?.last_gap
                  ? `Last gap ${formatRange(history.coverage.last_gap.start, history.coverage.last_gap.end)}`
                  : "Every Bee conversation of the last 7 days has been analysed"}
              </div>
            </div>
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex h-3 rounded overflow-hidden gap-px bg-black/40 border border-white/5">
              {(weekCoverage?.buckets || []).map((b) => (
                <div
                  key={b.start}
                  className={`flex-1 ${BUCKET_CLASS[bucketTone(b)]}`}
                  title={`${formatRange(b.start, b.end)} — gap ${formatDuration(b.gap_seconds)}`}
                />
              ))}
            </div>
            <div className="mt-1 font-mono text-[8px] text-secondary tracking-widest uppercase">LAST 7 DAYS · COVERAGE</div>
          </div>
          {historyRunId && historyState.tone === "running" && <BackfillStopButton runId={historyRunId} />}
          <button
            onClick={onOpenBackfill}
            className="px-4 py-2.5 rounded-xl border border-sky-500/40 bg-sky-950/30 hover:bg-sky-950/60 text-sky-300 font-mono text-[10px] font-bold tracking-widest uppercase transition-all shrink-0"
          >
            ⏪ ANALYSE PAST PERIOD…
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg">
        {/* SECTOR 01: Peace of Mind */}
        <div className="lg:col-span-8 card-elevated p-space-xl bg-surface-container-low border-surface-container-highest rounded-2xl flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-6 pb-3 border-b border-white/5">
              <div className="font-mono text-[10px] text-primary tracking-[0.2em] uppercase flex items-center gap-2 font-bold">
                <span className="text-amber-400">SECTOR 01 //</span> Peace of Mind (Acoustic Corroborations)
              </div>
              <button
                onClick={() => setActiveTab("peace")}
                className="font-mono text-[9px] text-amber-400 hover:underline uppercase tracking-widest"
              >
                VIEW ALL ({actions.length}) →
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-space-md">
              {actions.slice(0, 4).map((action, idx) => (
                <div
                  key={action.id || idx}
                  className="bg-[#121419] border border-surface-container-highest hover:border-emerald-500/40 rounded-xl p-space-lg flex flex-col justify-between transition-colors"
                >
                  <div>
                    <div className="flex items-center justify-between mb-2 gap-2">
                      <DomainBadge domain={action.domain} />
                      <div className="flex items-center gap-1.5">
                        <RecoveredBadge entity={action} />
                        <StatusBadge status="verified" size="sm" />
                      </div>
                    </div>
                    <div className="font-serif text-[20px] text-primary mb-2 capitalize">
                      {action.action_type.replace(/_/g, " ")}
                    </div>

                    <div className="bg-[#0b0c0f] border border-white/5 rounded-lg p-3 mb-4">
                      <div className="font-mono text-[8px] text-secondary tracking-widest mb-1 uppercase">
                        Verified {action.timestamp ? action.timestamp.split("T")[1]?.substring(0, 8) : "Recently"}
                      </div>
                      <p className="font-sans text-body-xs text-secondary leading-relaxed italic line-clamp-2">
                        "{action.raw_statement}"
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-2 border-t border-white/5">
                    <div className="font-mono text-[9px] text-secondary tracking-widest uppercase">
                      {(action.confidence * 100).toFixed(1)}% CONFIDENCE
                    </div>
                    <button
                      onClick={() => {
                        speakAlexaReassurance(
                          `EXAMEN Corroboration: Your ${action.action_type.replace(/_/g, " ")} is verified safe.`
                        );
                      }}
                      className="text-amber-400 hover:text-amber-300 font-mono text-[9px] tracking-wider uppercase flex items-center gap-1"
                    >
                      <span>💬</span>
                      <span>REASSURE</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* SECTOR 02: Daily Routines */}
        <div className="lg:col-span-4 card-elevated p-space-xl bg-surface-container-low border-surface-container-highest rounded-2xl flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-6 pb-3 border-b border-white/5">
              <div className="font-mono text-[10px] text-primary tracking-[0.2em] uppercase font-bold">
                <span className="text-amber-400">SECTOR 02 //</span> Daily Routines
              </div>
              <span className="font-mono text-[9px] text-emerald-400 font-bold tracking-widest uppercase">
                {completedTasks} / {tasks.length} COMPLETE
              </span>
            </div>

            {/* Progress Bar */}
            <div className="h-1.5 bg-surface-container-highest rounded-full mb-6 overflow-hidden">
              <div
                className="h-full bg-emerald-400 transition-all duration-500"
                style={{
                  width: `${tasks.length ? (completedTasks / tasks.length) * 100 : 0}%`,
                }}
              />
            </div>

            <div className="space-y-3">
              {tasks.slice(0, 4).map((task) => {
                const isDone = task.status === "completed";
                return (
                  <div
                    key={task.id}
                    onClick={() => handleToggleRoutine(task)}
                    className="flex items-start gap-3 p-3 rounded-xl bg-[#121419] border border-white/5 hover:border-amber-400/50 transition-all cursor-pointer"
                  >
                    <div
                      className={`w-5 h-5 rounded-lg flex items-center justify-center shrink-0 mt-0.5 transition-colors ${
                        isDone
                          ? "bg-emerald-500 text-black font-bold"
                          : "border border-zinc-600 text-transparent"
                      }`}
                    >
                      {isDone && <span className="text-xs">✓</span>}
                    </div>

                    <div className="flex-1 min-w-0">
                      <div
                        className={`font-sans text-body-sm mb-0.5 flex items-center justify-between ${
                          isDone ? "text-secondary line-through opacity-70" : "text-primary font-medium"
                        }`}
                      >
                        <span className="truncate">{task.title}</span>
                        <span className="font-mono text-[8px] text-secondary no-underline shrink-0 ml-2">
                          {task.scheduled_time || "DAILY"}
                        </span>
                      </div>
                      <div className="font-mono text-[9px] text-secondary uppercase opacity-60">
                        {task.domain}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="mt-6 pt-4 border-t border-white/5 flex items-center justify-between font-mono text-[9px] text-secondary uppercase tracking-widest">
            <button
              onClick={() => setActiveTab("routines")}
              className="text-amber-400 hover:underline"
            >
              MANAGE ROUTINES ({tasks.length}) →
            </button>
            <span>INGRESS: {statusData?.telemetry?.sensor_mesh?.toUpperCase() || "EDGE STANDBY"}</span>
          </div>
        </div>

        {/* BOTTOM ROW: Social & Topics Fast Navigation */}
        <div className="lg:col-span-12 grid grid-cols-1 sm:grid-cols-2 gap-space-lg">
          {/* Social Rolodex Card */}
          <div
            onClick={() => setActiveTab("social")}
            className="card-elevated p-space-xl bg-surface-container-low border-surface-container-highest rounded-2xl flex items-center justify-between cursor-pointer hover:border-amber-400 transition-all group"
          >
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-surface-container-highest flex items-center justify-center text-primary text-xl group-hover:scale-110 transition-transform">
                👤
              </div>
              <div>
                <div className="font-mono text-[9px] text-amber-400 tracking-[0.2em] uppercase font-bold mb-1">
                  SECTOR 03 // SOCIAL ROLODEX
                </div>
                <div className="font-serif text-[22px] text-primary">
                  {contacts.length} Encounters & Bilateral Promises
                </div>
              </div>
            </div>
            <span className="font-mono text-[10px] text-secondary group-hover:text-primary transition-colors">
              OPEN →
            </span>
          </div>

          {/* Topic Dossiers Card */}
          <div
            onClick={() => setActiveTab("topics")}
            className="card-elevated p-space-xl bg-surface-container-low border-surface-container-highest rounded-2xl flex items-center justify-between cursor-pointer hover:border-cyan-400 transition-all group"
          >
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-surface-container-highest flex items-center justify-center text-primary text-xl group-hover:scale-110 transition-transform">
                📚
              </div>
              <div>
                <div className="font-mono text-[9px] text-cyan-400 tracking-[0.2em] uppercase font-bold mb-1">
                  SECTOR 04 // TOPIC DOSSIERS
                </div>
                <div className="font-serif text-[22px] text-primary">
                  {topics.length} Citation-Backed Intelligence Reports
                </div>
              </div>
            </div>
            <span className="font-mono text-[10px] text-secondary group-hover:text-primary transition-colors">
              OPEN →
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
