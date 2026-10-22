import React, { useState } from "react";
import { PlannedTask, TaskChanges } from "@/types/schemas";
import { StatusBadge, DomainBadge } from "../ui/StatusBadge";
import { RecoveredBadge } from "../ui/RecoveredBadge";
import { SpeakerBadge } from "../ui/SpeakerBadge";
import { CreateTaskModal } from "../ui/CreateTaskModal";
import { CardActions } from "../ui/CardActions";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { TranscriptExcerpt } from "../ui/TranscriptExcerpt";
import { excerptLabels } from "@/utils/curation";

interface DailyRoutinesProps {
  routinesData: { tasks: PlannedTask[] } | undefined;
  statusData?: any;
  handleToggleRoutine: (task: PlannedTask) => void;
  handleAddRoutine: (title: string, domain: string, scheduled_time: string, recurrence?: string) => Promise<void>;
  handleDeleteRoutine?: (taskId: string) => Promise<void>;
  handleEditRoutine?: (taskId: string, changes: TaskChanges) => Promise<void>;
}

export function DailyRoutines({
  routinesData,
  statusData,
  handleToggleRoutine,
  handleAddRoutine,
  handleDeleteRoutine,
  handleEditRoutine,
}: DailyRoutinesProps) {
  const [statusFilter, setStatusFilter] = useState<"ALL" | "PENDING" | "COMPLETED">("ALL");
  const [domainFilter, setDomainFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingTask, setEditingTask] = useState<PlannedTask | null>(null);
  const [deletingTask, setDeletingTask] = useState<PlannedTask | null>(null);

  // Dynamic Telemetry State
  const sensorMesh = statusData?.telemetry?.sensor_mesh || "BEE TRANSCRIPTS";
  const latencyMetrics = statusData?.telemetry?.latency;
  const avgLatency = latencyMetrics?.average_ms
    ? `${latencyMetrics.average_ms}MS (AVG)`
    : "PASSIVE (STANDBY)";

  const tasks = routinesData?.tasks || [];

  const completedCount = tasks.filter((t) => t.status === "completed").length;
  const pendingCount = tasks.filter((t) => t.status === "pending").length;

  const safetyCount = tasks.filter((t) => (t.domain || "").toLowerCase() === "safety").length;
  const routineCount = tasks.filter((t) => (t.domain || "").toLowerCase() === "routine").length;
  const workCount = tasks.filter((t) => ["work_task", "work"].includes((t.domain || "").toLowerCase())).length;

  const filteredTasks = tasks.filter((t) => {
    const matchesStatus =
      statusFilter === "ALL" ||
      (statusFilter === "PENDING" && t.status === "pending") ||
      (statusFilter === "COMPLETED" && t.status === "completed");

    const tDomain = (t.domain || "").toLowerCase();
    const matchesDomain =
      domainFilter === "ALL" ||
      tDomain === domainFilter.toLowerCase() ||
      (domainFilter === "work_task" && (tDomain === "work_task" || tDomain === "work"));

    const searchLower = searchQuery.toLowerCase().trim();
    const matchesSearch =
      !searchLower ||
      t.title.toLowerCase().includes(searchLower) ||
      (t.domain || "").toLowerCase().includes(searchLower) ||
      (t.scheduled_time || "").toLowerCase().includes(searchLower);

    return matchesStatus && matchesDomain && matchesSearch;
  });

  return (
    <div className="space-y-space-lg animate-in fade-in max-w-[1300px] mx-auto relative">
      {/* ADD ROUTINE MODAL (Clean fixed viewport positioning) */}
      <CreateTaskModal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        onSubmit={async (title, domain, scheduledTime, recurrence) => {
          await handleAddRoutine(title, domain, scheduledTime, recurrence);
        }}
      />

      {/* EDIT ROUTINE MODAL */}
      {handleEditRoutine && (
        <CreateTaskModal
          mode="edit"
          isOpen={!!editingTask}
          initial={
            editingTask
              ? {
                  title: editingTask.title,
                  domain: editingTask.domain,
                  scheduledTime: editingTask.scheduled_time || "",
                  recurrence: editingTask.recurrence || "none",
                }
              : undefined
          }
          onClose={() => setEditingTask(null)}
          onSubmit={async (title, domain, scheduledTime, recurrence) => {
            if (!editingTask) return;
            await handleEditRoutine(editingTask.id, {
              title,
              domain: domain as TaskChanges["domain"],
              scheduled_time: scheduledTime,
              recurrence: recurrence as TaskChanges["recurrence"],
            });
          }}
        />
      )}

      {handleDeleteRoutine && (
        <ConfirmDialog
          isOpen={!!deletingTask}
          title={`Delete "${deletingTask?.title || ""}"?`}
          body="The routine is removed from your checklist."
          consequences={
            deletingTask?.origin === "social_commitment"
              ? "The commitment it was scheduled from stays open in the Social Rolodex."
              : undefined
          }
          onConfirm={() => handleDeleteRoutine((deletingTask as PlannedTask).id)}
          onClose={() => setDeletingTask(null)}
        />
      )}

      {/* Screen Header Banner */}
      <div className="card-elevated p-space-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-space-lg mb-space-lg bg-surface-container-low border-surface-container-highest">
        <div className="max-w-3xl">
          <div className="font-mono text-label-sm text-amber-400/90 uppercase tracking-widest mb-2 flex items-center gap-2">
            <span className="w-1.5 h-1.5 bg-amber-400 rounded-full inline-block"></span>
            OPERATIONAL DIRECTIVE • SECTOR 04 // PASSIVE ROUTINES
          </div>
          <h2 className="font-serif text-[32px] leading-tight text-primary uppercase mb-4 font-normal">
            Passive Routine Tracking & Domestic Safety Checklist
          </h2>
          <p className="font-sans text-body-md text-secondary leading-relaxed max-w-3xl pr-4">
            EXAMEN passively monitors recurring household routines, appliance disconnects, and perimeter closures without requiring manual checkmarks. When you mention a completed check near the Bee, its transcript closes the matching routine; each card shows the words it came from.
          </p>
        </div>
        <div className="shrink-0 flex flex-col items-end gap-3 self-center md:self-auto mt-4 md:mt-0">
          <StatusBadge status="nominal" label={sensorMesh.toUpperCase()} size="md" />
          <div className="font-mono text-[9px] text-secondary uppercase text-right tracking-[0.2em] pr-2">
            LATENCY: {avgLatency} • LOCAL PRIVACY ENCLAVE
          </div>
        </div>
      </div>

      {/* 4 Metrics Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-space-md mb-space-xl">
        {/* Card 1: Cycle Completion */}
        <div className="card-elevated p-space-lg flex flex-col justify-between bg-[#121419] border border-white/5">
          <div className="flex items-center justify-between mb-6">
            <div className="font-mono text-[10px] text-secondary uppercase tracking-widest">
              CYCLE COMPLETION
            </div>
            <span className="text-emerald-400 text-lg">✓</span>
          </div>
          <div>
            <div className="flex items-baseline gap-2 mb-3">
              <span className="font-serif text-[38px] text-primary">
                {completedCount} / {tasks.length}
              </span>
              <span className="font-mono text-[9px] text-secondary uppercase tracking-widest">
                VERIFIED
              </span>
            </div>
            <div className="h-1.5 bg-surface-container-highest rounded-full overflow-hidden">
              <div
                className="h-full bg-emerald-400 transition-all duration-500"
                style={{
                  width: `${tasks.length ? (completedCount / tasks.length) * 100 : 0}%`,
                }}
              />
            </div>
          </div>
        </div>

        {/* Card 2: Next Cadence */}
        <div className="card-elevated p-space-lg flex flex-col justify-between bg-[#121419] border border-white/5">
          <div className="flex items-center justify-between mb-6">
            <div className="font-mono text-[10px] text-secondary uppercase tracking-widest">
              NEXT ANCHOR CADENCE
            </div>
            <span className="text-amber-400 text-lg">⏱️</span>
          </div>
          <div>
            <div className="font-serif text-[32px] text-primary mb-1">18:30:00</div>
            <div className="font-mono text-[9px] text-secondary uppercase tracking-widest mb-1">
              EVENING INGRESS PROTOCOL
            </div>
            <div className="font-mono text-[9px] text-amber-400/80 uppercase tracking-widest">
              {pendingCount} ANCHORS ACTIVE
            </div>
          </div>
        </div>

        {/* Card 3: Perimeter Integrity */}
        <div className="card-elevated p-space-lg flex flex-col justify-between bg-[#121419] border border-white/5">
          <div className="flex items-center justify-between mb-6">
            <div className="font-mono text-[10px] text-secondary uppercase tracking-widest">
              PERIMETER INTEGRITY
            </div>
            <span className="text-cyan-400 text-lg">🛡️</span>
          </div>
          <div>
            <div className="font-serif text-[28px] text-primary mb-1 tracking-wide">CALIBRATED</div>
            <div className="font-mono text-[9px] text-secondary uppercase tracking-widest mb-1">
              ALL VALVES & SASHES SEALED
            </div>
            <div className="font-mono text-[9px] text-emerald-400 uppercase tracking-widest flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
              ZERO ANOMALIES LOGGED
            </div>
          </div>
        </div>

        {/* Card 4: Action Button */}
        <div className="card-elevated p-space-lg flex flex-col justify-between bg-[#121419] border border-white/5">
          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="font-mono text-[10px] text-secondary uppercase tracking-widest">
                ROUTINE SUPERVISION
              </div>
              <span className="text-amber-400 text-lg">➕</span>
            </div>
            <div className="font-sans text-body-xs text-secondary leading-relaxed mb-4">
              Track recurring checks closed by what you say.
            </div>
          </div>
          <button
            onClick={() => setShowAddModal(true)}
            className="w-full py-2.5 px-4 bg-primary hover:bg-surface-tint text-background font-mono text-[11px] font-bold tracking-widest rounded-lg transition-all shadow-md flex items-center justify-center gap-2"
          >
            <span>+</span>
            <span>ADD ROUTINE</span>
          </button>
        </div>
      </div>

      {/* Search & Filter Row */}
      <div className="flex flex-col gap-4 mb-space-lg border-b border-surface-container-highest pb-6">
        <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
          {/* Search input */}
          <div className="flex-1 max-w-md relative">
            <span className="absolute left-4 top-1/2 -translate-y-1/2 text-secondary text-sm">🔍</span>
            <input
              type="text"
              placeholder="Search routines by title, domain, or time..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-[#121419] border border-surface-container-highest rounded-full py-2.5 pl-10 pr-10 text-body-sm font-sans text-primary placeholder-zinc-500 focus:outline-none focus:border-primary transition-colors"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-white font-mono text-xs w-5 h-5 rounded-full flex items-center justify-center bg-white/5 hover:bg-white/10 transition-colors"
                title="Clear search"
              >
                ✕
              </button>
            )}
          </div>

          {/* Status Filters */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[9px] text-secondary uppercase tracking-widest mr-1">Status:</span>
            <button
              onClick={() => setStatusFilter("ALL")}
              className={`px-3.5 py-1.5 rounded-full font-mono text-[10px] font-bold tracking-widest transition-colors ${
                statusFilter === "ALL"
                  ? "bg-primary text-background shadow"
                  : "text-secondary hover:bg-surface-container hover:text-primary"
              }`}
            >
              ALL ({tasks.length})
            </button>
            <button
              onClick={() => setStatusFilter("PENDING")}
              className={`px-3.5 py-1.5 rounded-full font-mono text-[10px] font-bold tracking-widest transition-colors flex items-center gap-1.5 ${
                statusFilter === "PENDING"
                  ? "bg-amber-500 text-black shadow"
                  : "text-amber-400/80 bg-amber-950/20 border border-amber-500/20 hover:bg-amber-950/40"
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
              <span>PENDING ({pendingCount})</span>
            </button>
            <button
              onClick={() => setStatusFilter("COMPLETED")}
              className={`px-3.5 py-1.5 rounded-full font-mono text-[10px] font-bold tracking-widest transition-colors flex items-center gap-1.5 ${
                statusFilter === "COMPLETED"
                  ? "bg-emerald-500 text-black shadow"
                  : "text-emerald-400/80 bg-emerald-950/20 border border-emerald-500/20 hover:bg-emerald-950/40"
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              <span>COMPLETED ({completedCount})</span>
            </button>
          </div>
        </div>

        {/* Domain Filters Row */}
        <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-white/5">
          <span className="font-mono text-[9px] text-secondary uppercase tracking-widest mr-1">Domain:</span>
          <button
            onClick={() => setDomainFilter("ALL")}
            className={`px-3 py-1 rounded-lg font-mono text-[9px] font-bold tracking-wider uppercase transition-colors ${
              domainFilter === "ALL"
                ? "bg-zinc-700 text-white font-bold"
                : "text-zinc-400 hover:text-white hover:bg-white/5"
            }`}
          >
            All Domains
          </button>
          <button
            onClick={() => setDomainFilter("safety")}
            className={`px-3 py-1 rounded-lg font-mono text-[9px] font-bold tracking-wider uppercase transition-colors flex items-center gap-1.5 ${
              domainFilter.toLowerCase() === "safety"
                ? "bg-amber-500 text-black shadow font-bold"
                : "text-amber-300 bg-amber-950/40 border border-amber-500/30 hover:bg-amber-950/70"
            }`}
          >
            <span>🛡️</span>
            <span>Safety ({safetyCount})</span>
          </button>
          <button
            onClick={() => setDomainFilter("routine")}
            className={`px-3 py-1 rounded-lg font-mono text-[9px] font-bold tracking-wider uppercase transition-colors flex items-center gap-1.5 ${
              domainFilter.toLowerCase() === "routine"
                ? "bg-sky-500 text-black shadow font-bold"
                : "text-sky-300 bg-sky-950/40 border border-sky-500/30 hover:bg-sky-950/70"
            }`}
          >
            <span>📋</span>
            <span>Routine ({routineCount})</span>
          </button>
          <button
            onClick={() => setDomainFilter("work_task")}
            className={`px-3 py-1 rounded-lg font-mono text-[9px] font-bold tracking-wider uppercase transition-colors flex items-center gap-1.5 ${
              ["work_task", "work"].includes(domainFilter.toLowerCase())
                ? "bg-indigo-500 text-white shadow font-bold"
                : "text-indigo-300 bg-indigo-950/40 border border-indigo-500/30 hover:bg-indigo-950/70"
            }`}
          >
            <span>💼</span>
            <span>Work Task ({workCount})</span>
          </button>
        </div>
      </div>

      {/* Routines Grid */}
      {filteredTasks.length === 0 ? (
        <div className="p-12 text-center border border-dashed border-surface-container-highest rounded-2xl bg-[#121419]">
          <div className="text-3xl mb-3">📋</div>
          <div className="font-serif text-xl text-primary mb-2">No Monitored Routines Match Filter</div>
          <p className="font-sans text-secondary text-sm mb-6 max-w-md mx-auto">
            {searchQuery
              ? `No routines found matching "${searchQuery}". Try clearing search or choosing another filter.`
              : "No routines in this domain yet. Add a new monitored routine to start tracking."}
          </p>
          <button
            onClick={() => setShowAddModal(true)}
            className="px-5 py-2.5 rounded-lg bg-primary text-background font-mono text-[10px] tracking-widest font-bold uppercase"
          >
            + Create Routine
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-space-lg">
          {filteredTasks.map((task, idx) => {
            const isCompleted = task.status === "completed";

            return (
              <div
                key={task.id}
                className={`card-elevated p-space-xl flex flex-col rounded-2xl transition-all duration-200 border ${
                  isCompleted
                    ? "bg-[#101317] border-emerald-950/60 hover:border-emerald-500/40"
                    : "bg-[#14161c] border-surface-container-highest hover:border-amber-500/40"
                }`}
              >
                {/* Card Top Row */}
                <div className="flex items-center justify-between mb-6 pb-3 border-b border-white/5">
                  <div className="font-mono text-[10px] text-secondary tracking-[0.2em] uppercase flex items-center gap-2">
                    <span>STEP {String(idx + 1).padStart(2, "0")}</span>
                    <span className="opacity-40">•</span>
                    <span className="text-primary font-bold">
                      {task.scheduled_time || "SCHEDULED"} UTC
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <DomainBadge domain={task.domain} />
                    <button
                      onClick={() => handleToggleRoutine(task)}
                      className="cursor-pointer transition-transform hover:scale-105"
                      title="Click to toggle status"
                    >
                      <StatusBadge status={task.status} />
                    </button>
                  </div>
                </div>

                {/* Title & Icon */}
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h3
                      className={`font-serif text-[26px] leading-tight transition-colors ${
                        isCompleted ? "text-primary/90" : "text-primary font-semibold"
                      }`}
                    >
                      {task.title}
                    </h3>
                    <div className="font-mono text-[9px] text-secondary tracking-widest uppercase mt-1 flex items-center gap-2 flex-wrap">
                      <span>Recurrence: {task.recurrence || "daily"} • Created {task.created_at ? task.created_at.split("T")[0] : "today"}</span>
                      <RecoveredBadge entity={task} />
                      <SpeakerBadge speaker={task.speaker} />
                    </div>
                  </div>

                  <button
                    onClick={() => handleToggleRoutine(task)}
                    className={`w-12 h-12 rounded-xl flex items-center justify-center shrink-0 transition-all ${
                      isCompleted
                        ? "bg-emerald-950/60 border border-emerald-500/40 text-emerald-400"
                        : "bg-surface-container-highest border border-white/5 text-secondary hover:text-amber-400"
                    }`}
                    title={isCompleted ? "Mark Pending" : "Mark Completed"}
                  >
                    {isCompleted ? (
                      <span className="text-xl">✓</span>
                    ) : (
                      <span className="text-lg">○</span>
                    )}
                  </button>
                </div>

                {/* Transcript excerpts: where the routine came from and what completed it */}
                {(() => {
                  const excerpts = excerptLabels(task);
                  if (excerpts.length === 0) {
                    return (
                      <p className="font-sans text-body-sm text-secondary mb-6">
                        Created manually{task.created_at ? ` · ${task.created_at.split("T")[0]}` : ""}
                      </p>
                    );
                  }
                  return (
                    <div className="space-y-3 mb-6">
                      {excerpts.map((ex) => (
                        <TranscriptExcerpt key={ex.label} label={ex.label} text={ex.text} meta={ex.meta} />
                      ))}
                    </div>
                  );
                })()}

                {/* Footer Controls */}
                <div className="mt-auto flex items-center justify-between font-mono text-[10px] text-secondary tracking-widest uppercase border-t border-white/5 pt-4">
                  <div className="flex items-center gap-2">
                    <CardActions
                      noun="routine"
                      onEdit={handleEditRoutine ? () => setEditingTask(task) : undefined}
                      onDelete={handleDeleteRoutine ? () => setDeletingTask(task) : undefined}
                    />
                  </div>

                  <button
                    onClick={() => handleToggleRoutine(task)}
                    className="hover:text-primary transition-colors cursor-pointer text-amber-400 font-bold"
                  >
                    {isCompleted ? "Mark Pending ↺" : "Verify Complete ✓"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
