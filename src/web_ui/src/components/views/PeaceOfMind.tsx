import React, { useState } from "react";
import { VerifiedAction } from "@/types/schemas";
import { ScreenHeader } from "../ui/ScreenHeader";
import { StatusBadge, DomainBadge } from "../ui/StatusBadge";
import { RecoveredBadge } from "../ui/RecoveredBadge";
import { SpeakerBadge } from "../ui/SpeakerBadge";
import { CreateActionModal } from "../ui/CreateActionModal";
import { playAcousticVerificationTone, speakAlexaReassurance } from "@/utils/audioEffects";

interface PeaceOfMindProps {
  actionsData: { actions: VerifiedAction[] } | undefined;
  statusData?: any;
  onAddAction?: (statement: string) => Promise<void>;
}

export function PeaceOfMind({ actionsData, statusData, onAddAction }: PeaceOfMindProps) {
  const [confidenceFilter, setConfidenceFilter] = useState<"ALL" | "HIGH">("ALL");
  const [domainFilter, setDomainFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [showAddModal, setShowAddModal] = useState(false);
  const [activeAudioId, setActiveAudioId] = useState<string | null>(null);

  // Dynamic Telemetry Data
  const sensorMesh = statusData?.telemetry?.sensor_mesh || "BEE HARDWARE (STANDBY)";
  const isBeeConnected = statusData?.telemetry?.bee_device?.connected;
  const procModel = (
    statusData?.telemetry?.processing_model?.reasoner ||
    statusData?.config?.reasoner_model ||
    "AWS BEDROCK AGENTCORE"
  ).toUpperCase();
  const latencyMetrics = statusData?.telemetry?.latency;
  const avgLatency = latencyMetrics?.average_ms
    ? `${latencyMetrics.average_ms}ms (AVG)`
    : "PASSIVE STANDBY";

  const actions = actionsData?.actions || [];
  const safetyCount = actions.filter((a) => (a.domain || "").toLowerCase() === "safety").length;
  const routineCount = actions.filter((a) => (a.domain || "").toLowerCase() === "routine").length;
  const workCount = actions.filter((a) => ["work_task", "work"].includes((a.domain || "").toLowerCase())).length;
  const highConfCount = actions.filter((a) => a.confidence >= 0.95).length;

  const avgConfidence = actions.length > 0
    ? (actions.reduce((acc, a) => acc + a.confidence, 0) / actions.length) * 100
    : 0;

  const filteredActions = actions.filter((a) => {
    const matchesConfidence = confidenceFilter === "ALL" || a.confidence >= 0.95;

    const aDomain = (a.domain || "").toLowerCase();
    const matchesDomain =
      domainFilter === "ALL" ||
      aDomain === domainFilter.toLowerCase() ||
      (domainFilter === "work_task" && (aDomain === "work_task" || aDomain === "work"));

    const searchLower = searchQuery.toLowerCase().trim();
    const matchesSearch =
      !searchLower ||
      a.action_type.toLowerCase().includes(searchLower) ||
      a.raw_statement.toLowerCase().includes(searchLower) ||
      (a.domain || "").toLowerCase().includes(searchLower);

    return matchesConfidence && matchesDomain && matchesSearch;
  });

  const handlePlayCitation = (action: VerifiedAction) => {
    setActiveAudioId(action.id);
    playAcousticVerificationTone();
    setTimeout(() => setActiveAudioId(null), 1200);
  };

  const handleEchoReassurance = (action: VerifiedAction) => {
    setActiveAudioId(action.id);
    const text = `EXAMEN Corroboration: Your ${action.action_type.replace(/_/g, " ")} is verified with ${(action.confidence * 100).toFixed(1)} percent certainty.`;
    speakAlexaReassurance(text);
    setTimeout(() => setActiveAudioId(null), 2500);
  };

  return (
    <div className="space-y-space-lg animate-in fade-in max-w-[1400px] mx-auto">
      {/* Modal for adding custom action statement */}
      {onAddAction && (
        <CreateActionModal
          isOpen={showAddModal}
          onClose={() => setShowAddModal(false)}
          onSubmit={async (statement) => {
            await onAddAction(statement);
          }}
        />
      )}

      {/* Screen Header */}
      <ScreenHeader
        directive="SCREEN PURPOSE // ARCHITECTURAL CONTEXT"
        title="DOMESTIC REASSURANCE & ACOUSTIC PROOF"
        description={
          <>
            The Peace of Mind sector captures spontaneous verbal notes, appliance disconnects, and ad-hoc domestic checks without tedious manual app logging. EXAMEN passively corroborates these actions via the Bee wearable's acoustic sensors and provides reassuring voice and visual proof.
          </>
        }
        rightElement={
          <div className="bg-[#121419] border border-surface-container-highest rounded-xl p-4 font-mono w-[320px]">
            <div className="flex justify-between items-center text-[8px] text-secondary tracking-[0.2em] uppercase mb-2">
              <span>SENSOR MESH</span>
              <span className={`font-bold ${isBeeConnected ? "text-emerald-400" : "text-amber-400"}`}>
                {sensorMesh.toUpperCase()}
              </span>
            </div>
            <div className="flex justify-between items-center text-[8px] text-secondary tracking-[0.2em] uppercase mb-2">
              <span>PROCESSING MODEL</span>
              <span className="text-primary font-bold truncate max-w-[180px]" title={procModel}>
                {procModel}
              </span>
            </div>
            <div className="flex justify-between items-center text-[8px] text-secondary tracking-[0.2em] uppercase">
              <span>LATENCY OVERHEAD</span>
              <span className="text-emerald-400 font-bold">
                {avgLatency}
              </span>
            </div>
          </div>
        }
      />

      {/* KPI Full Width Card */}
      <div className="card-elevated p-space-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-space-lg mb-space-lg bg-surface-container-low border-surface-container-highest rounded-2xl">
        <div className="flex items-center gap-space-lg">
          <div className="w-16 h-16 rounded-2xl bg-[#121419] border border-surface-container-highest flex items-center justify-center text-emerald-400 shrink-0 text-2xl shadow-lg">
            🛡️
          </div>
          <div>
            <div className="flex items-center gap-4 mb-2">
              <h3 className="font-serif text-[28px] text-primary">Unplanned Reminders & Notes</h3>
              <StatusBadge status="verified" label={`${actions.length} CAPTURED TODAY`} />
            </div>
            <div className="font-sans text-body-sm text-secondary">
              Spontaneous affirmations • Appliance checks • Door deadbolts • Zero cloud egress
            </div>
          </div>
        </div>

        <div className="flex items-center gap-space-xl shrink-0 md:border-l border-surface-container-highest md:pl-space-xl">
          <div className="flex flex-col">
            <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-1">
              AVERAGE CONFIDENCE
            </div>
            <div className="flex items-baseline gap-1 font-serif text-[44px] text-primary">
              {avgConfidence.toFixed(1)}
              <span className="text-[20px] text-emerald-400">%</span>
            </div>
          </div>
          {onAddAction && (
            <button
              onClick={() => setShowAddModal(true)}
              className="btn-primary font-mono text-[11px] font-bold tracking-[0.2em] bg-primary text-background px-6 py-3.5 rounded-lg hover:bg-surface-tint transition-all shadow-md ml-4"
            >
              + RECORD ACTION
            </button>
          )}
        </div>
      </div>

      {/* Search & Filter Row */}
      <div className="flex flex-col gap-4 mb-space-xl border-b border-surface-container-highest pb-6">
        <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
          {/* Search */}
          <div className="flex-1 max-w-md relative">
            <span className="absolute left-4 top-1/2 -translate-y-1/2 text-secondary text-sm">🔍</span>
            <input
              type="text"
              placeholder="Search actions by device, utterance, or domain..."
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

          {/* Confidence Filter Tabs */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[9px] text-secondary uppercase tracking-widest mr-1">Certainty:</span>
            <button
              onClick={() => setConfidenceFilter("ALL")}
              className={`px-3.5 py-1.5 rounded-full font-mono text-[10px] font-bold tracking-widest transition-colors ${
                confidenceFilter === "ALL"
                  ? "bg-primary text-background shadow"
                  : "text-secondary hover:bg-surface-container hover:text-primary"
              }`}
            >
              ALL ({actions.length})
            </button>
            <button
              onClick={() => setConfidenceFilter("HIGH")}
              className={`px-3.5 py-1.5 rounded-full font-mono text-[10px] font-bold tracking-widest transition-colors flex items-center gap-1.5 ${
                confidenceFilter === "HIGH"
                  ? "bg-emerald-500 text-black shadow"
                  : "text-emerald-400/80 bg-emerald-950/20 border border-emerald-500/20 hover:bg-emerald-950/40"
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              <span>HIGH CONFIDENCE &gt;95% ({highConfCount})</span>
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

      {/* Action Cards Grid */}
      {filteredActions.length === 0 ? (
        <div className="p-12 text-center border border-dashed border-surface-container-highest rounded-2xl bg-[#121419]">
          <div className="text-3xl mb-3">🛡️</div>
          <div className="font-serif text-xl text-primary mb-2">No Verified Actions Found</div>
          <p className="font-sans text-secondary text-sm mb-6 max-w-md mx-auto">
            {searchQuery
              ? `No actions matched "${searchQuery}". Try a different keyword.`
              : "No actions verified yet. Try simulating an utterance or clicking '+ Record Action'."}
          </p>
          {onAddAction && (
            <button
              onClick={() => setShowAddModal(true)}
              className="px-5 py-2.5 rounded-lg bg-primary text-background font-mono text-[10px] tracking-widest font-bold uppercase"
            >
              + Record New Action
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-space-lg">
          {filteredActions.map((action, idx) => {
            const isAudioActive = activeAudioId === action.id;

            return (
              <div
                key={action.id || idx}
                className="card-elevated p-space-xl flex flex-col bg-surface-container-low border-surface-container-highest rounded-2xl hover:border-emerald-500/40 transition-all duration-200"
              >
                {/* Header */}
                <div className="flex items-start justify-between mb-6 pb-3 border-b border-white/5">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-xl bg-[#121419] border border-surface-container-highest flex items-center justify-center text-primary shrink-0 text-xl shadow-md">
                      {action.domain === "safety" ? "🛡️" : action.domain === "work_task" ? "💼" : "📋"}
                    </div>
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <DomainBadge domain={action.domain} />
                        <RecoveredBadge entity={action} />
                        <SpeakerBadge speaker={action.speaker} />
                        <span className="font-mono text-[8px] text-secondary tracking-widest uppercase">
                          HASH: {action.id ? action.id.substring(0, 8) : "ACT_0" + idx}
                        </span>
                      </div>
                      <h3 className="font-serif text-[26px] text-primary leading-tight font-normal capitalize">
                        {action.action_type.replace(/_/g, " ")}
                      </h3>
                    </div>
                  </div>
                  <StatusBadge status="verified" label="VERIFIED" />
                </div>

                {/* Subtitle / Timestamp */}
                <div className="flex items-center justify-between font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-4">
                  <span>ACOUSTIC DETENT + VOCAL PROOF</span>
                  <span className="text-emerald-400 font-bold">
                    {action.timestamp ? action.timestamp.replace("T", " ").substring(11, 19) : "RECENT"} UTC
                  </span>
                </div>

                {/* Raw Spoken Statement */}
                <div className="bg-[#121419] border border-surface-container-highest rounded-xl p-4 mb-6">
                  <div className="font-mono text-[8px] text-secondary tracking-widest uppercase mb-1">
                    Captured Spoken Utterance
                  </div>
                  <p className="font-sans text-body-md text-primary leading-relaxed italic">
                    "{action.raw_statement}"
                  </p>
                </div>

                {/* Simulated Waveform Bar */}
                <div className="bg-[#101217] border border-surface-container-highest rounded-xl p-3 mb-6">
                  <div className="flex items-center justify-between font-mono text-[8px] text-secondary uppercase tracking-widest mb-2">
                    <span className="flex items-center gap-1.5">
                      <span className={`w-1.5 h-1.5 rounded-full ${isAudioActive ? "bg-amber-400 animate-ping" : "bg-emerald-400"}`}></span>
                      SPECTRAL ENVELOPE (1.2 kHz - 4.8 kHz)
                    </span>
                    <span className="text-emerald-400 font-bold">{(action.confidence * 100).toFixed(1)}% CONFIDENCE</span>
                  </div>
                  <svg
                    width="100%"
                    height="28"
                    viewBox="0 0 400 28"
                    preserveAspectRatio="none"
                    className={`transition-colors ${isAudioActive ? "text-amber-400" : "text-emerald-400/80"}`}
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                  >
                    <path d="M0,14 L120,14 L135,2 L150,26 L165,6 L180,24 L195,14 L400,14" />
                  </svg>
                </div>

                {/* Bottom Controls */}
                <div className="mt-auto flex items-center justify-between border-t border-surface-container-highest pt-4">
                  <div className="font-mono text-[10px] text-secondary tracking-[0.2em] uppercase">
                    CONFIDENCE:{" "}
                    <span className="text-emerald-400 font-bold">
                      {(action.confidence * 100).toFixed(1)}%
                    </span>
                  </div>

                  <div className="flex gap-2">
                    <button
                      onClick={() => handlePlayCitation(action)}
                      className="px-4 py-2 rounded-lg bg-surface-container-highest text-primary font-mono text-[9px] font-bold tracking-[0.2em] flex items-center gap-1.5 hover:bg-outline-variant transition-colors"
                      title="Play acoustic verification tone"
                    >
                      <span>🔊</span>
                      <span>PLAY CITATION</span>
                    </button>

                    <button
                      onClick={() => handleEchoReassurance(action)}
                      className="px-4 py-2 rounded-lg border border-surface-container-highest bg-transparent hover:bg-surface-container text-secondary hover:text-amber-300 font-mono text-[9px] tracking-[0.2em] transition-colors flex items-center gap-1.5"
                      title="Speak Alexa voice reassurance"
                    >
                      <span>💬</span>
                      <span>ECHO REASSURANCE</span>
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
