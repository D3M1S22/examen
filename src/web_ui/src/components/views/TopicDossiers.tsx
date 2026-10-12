import React, { useState } from "react";
import { BriefingReport } from "@/types/schemas";
import { ScreenHeader } from "../ui/ScreenHeader";
import { StatusBadge } from "../ui/StatusBadge";
import { TopicDetailModal } from "../ui/TopicDetailModal";
import { speakAlexaReassurance } from "@/utils/audioEffects";

interface TopicDossiersProps {
  topicsData: { topics: BriefingReport[] } | undefined;
  statusData?: any;
}

export function TopicDossiers({ topicsData, statusData }: TopicDossiersProps) {
  const [activeFilter, setActiveFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTopic, setSelectedTopic] = useState<BriefingReport | null>(null);
  const [broadcastedId, setBroadcastedId] = useState<string | null>(null);

  // Dynamic Telemetry State
  const reasonerModel = (
    statusData?.telemetry?.processing_model?.reasoner ||
    statusData?.config?.reasoner_model ||
    "AWS BEDROCK AGENTCORE"
  ).toUpperCase();
  const latencyMetrics = statusData?.telemetry?.latency;
  const avgLatency = latencyMetrics?.average_ms
    ? `${latencyMetrics.average_ms}MS (AVG)`
    : "BACKGROUND STANDBY";

  const topics = topicsData?.topics || [];
  const uniqueContexts = Array.from(new Set(topics.map((t) => t.context_type))).filter(Boolean);

  const filteredTopics = topics.filter((t) => {
    const matchesFilter = activeFilter === "ALL" || t.context_type === activeFilter;
    const searchLower = searchQuery.toLowerCase();
    const matchesSearch =
      !searchQuery ||
      t.topic_title.toLowerCase().includes(searchLower) ||
      (t.explanatory_synthesis || "").toLowerCase().includes(searchLower) ||
      (t.executive_summary || []).some((s) => s.toLowerCase().includes(searchLower)) ||
      (t.action_items || []).some((a) => a.toLowerCase().includes(searchLower)) ||
      (t.context_type || "").toLowerCase().includes(searchLower);

    return matchesFilter && matchesSearch;
  });

  const handleBroadcast = (topic: BriefingReport) => {
    setBroadcastedId(topic.id);
    const text = `Topic briefing for ${topic.topic_title}: ${topic.explanatory_synthesis || topic.executive_summary?.[0] || "Synthesized analysis completed."}`;
    speakAlexaReassurance(text);
    setTimeout(() => setBroadcastedId(null), 3000);
  };

  return (
    <div className="space-y-space-lg animate-in fade-in max-w-[1400px] mx-auto">
      {/* Detail Modal */}
      <TopicDetailModal
        topic={selectedTopic}
        isOpen={!!selectedTopic}
        onClose={() => setSelectedTopic(null)}
      />

      {/* Screen Header */}
      <ScreenHeader
        directive="COGNITIVE TELEMETRY SUBSYSTEM // AWS BEDROCK AGENTCORE"
        title="AUTONOMOUS TOPIC RESEARCH & ENRICHED DOSSIERS"
        description={
          <>
            Topic Dossiers serve as your ambient academic and technical research assistant. When listening to lectures, technical standups, or architectural debates, EXAMEN initiates deep background research, synthesizing ambient arguments into structured, citation-backed dossiers with core explanatory syntheses.
          </>
        }
        rightElement={
          <div className="flex flex-col items-end gap-1">
            <StatusBadge status="nominal" label="SYNTHESIS ENGINE RUNNING" size="md" />
            <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase">
              CADENCE: {avgLatency} • {reasonerModel}
            </div>
          </div>
        }
      />

      {/* Search & Filter Row */}
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4 mb-space-xl border-b border-surface-container-highest pb-6">
        {/* Search */}
        <div className="flex-1 max-w-md relative">
          <span className="absolute left-4 top-1/2 -translate-y-1/2 text-secondary text-sm">🔍</span>
          <input
            type="text"
            placeholder="Search dossiers by topic, thesis, keywords, or citations..."
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

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setActiveFilter("ALL")}
            className={`px-4 py-2 rounded-full font-mono text-[10px] font-bold tracking-widest transition-colors ${
              activeFilter === "ALL"
                ? "bg-primary text-background shadow"
                : "text-secondary hover:bg-surface-container hover:text-primary"
            }`}
          >
            ALL ({topics.length})
          </button>
          {uniqueContexts.map((ctx) => {
            const isSelected = activeFilter === ctx;
            const ctxCount = topics.filter((t) => t.context_type === ctx).length;
            const label = ctx ? ctx.replace(/_/g, " ").toUpperCase() : "GENERAL";
            return (
              <button
                key={ctx}
                onClick={() => setActiveFilter(ctx as string)}
                className={`px-4 py-2 rounded-full font-mono text-[10px] font-bold tracking-widest transition-colors flex items-center gap-1.5 ${
                  isSelected
                    ? "bg-amber-500 text-black shadow"
                    : "text-amber-400/80 bg-amber-950/20 border border-amber-500/20 hover:bg-amber-950/40"
                }`}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                <span>{label} ({ctxCount})</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Dossiers List */}
      {filteredTopics.length === 0 ? (
        <div className="p-12 text-center border border-dashed border-surface-container-highest rounded-2xl bg-[#121419]">
          <div className="text-3xl mb-3">📚</div>
          <div className="font-serif text-xl text-primary mb-2">No Topic Dossiers Found</div>
          <p className="font-sans text-secondary text-sm mb-6 max-w-md mx-auto">
            {searchQuery
              ? `No dossiers matched "${searchQuery}".`
              : "No dossiers synthesized yet. Run a tech discussion in the ambient simulator to trigger deep topic research."}
          </p>
        </div>
      ) : (
        <div className="space-y-space-lg">
          {filteredTopics.map((topic) => {
            const isBroadcasting = broadcastedId === topic.id;

            return (
              <div
                key={topic.id}
                className="card-elevated p-space-xl bg-surface-container-low border-surface-container-highest rounded-2xl flex flex-col gap-6 hover:border-amber-500/40 transition-all duration-200"
              >
                {/* Header Row */}
                <div className="flex flex-col md:flex-row items-start justify-between gap-4 pb-4 border-b border-white/5">
                  <div className="flex flex-col">
                    <div className="font-mono text-[9px] text-amber-400 tracking-[0.2em] uppercase flex items-center gap-2 mb-2 font-bold">
                      <span>DOSSIER #{topic.id.substring(0, 6).toUpperCase()}</span>
                      <span className="opacity-40">•</span>
                      <span className="text-secondary font-normal">
                        SYNTHESIZED {topic.created_at ? topic.created_at.split("T")[1]?.substring(0, 5) : "RECENT"} UTC
                      </span>
                    </div>

                    <h3 className="font-serif text-[32px] sm:text-[36px] text-primary leading-tight mb-2">
                      {topic.topic_title}
                    </h3>

                    <div className="flex items-center gap-2">
                      <span className="px-2.5 py-1 rounded bg-[#1c1f26] border border-white/5 font-mono text-[9px] text-secondary tracking-widest uppercase">
                        {topic.context_type?.replace(/_/g, " ").toUpperCase() || "GENERAL RESEARCH"}
                      </span>
                      <StatusBadge status="completed" label="SYNTHESIS COMPLETE" />
                    </div>
                  </div>

                  {/* Buttons */}
                  <div className="flex items-center gap-2 shrink-0 self-end md:self-center">
                    <button
                      onClick={() => setSelectedTopic(topic)}
                      className="px-5 py-2.5 rounded-lg border border-surface-container-highest bg-transparent hover:bg-surface-container text-secondary hover:text-primary font-mono text-[9px] tracking-[0.2em] flex items-center gap-2 transition-colors uppercase font-bold"
                      title="Open full research report"
                    >
                      <span>📖</span>
                      <span>ABSTRACT & DEEP DIVE</span>
                    </button>

                    <button
                      onClick={() => handleBroadcast(topic)}
                      className="px-5 py-2.5 rounded-lg border border-amber-500/50 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 font-mono text-[9px] tracking-[0.2em] font-bold flex items-center gap-2 transition-colors uppercase shadow-sm"
                      title="Broadcast topic to Alexa Echo Show"
                    >
                      <span>🔊</span>
                      <span>{isBroadcasting ? "SPEAKING..." : "BROADCAST TO ALEXA"}</span>
                    </button>
                  </div>
                </div>

                {/* Explanatory Synthesis Box (Next_steps highlight) */}
                {topic.explanatory_synthesis && (
                  <div className="bg-gradient-to-r from-amber-950/30 to-[#121419] border border-amber-500/30 rounded-xl p-4">
                    <div className="font-mono text-[9px] text-amber-300 tracking-[0.2em] uppercase font-bold mb-1 flex items-center gap-1.5">
                      <span>⚡</span>
                      <span>EXPLANATORY CONTEXTUAL SYNTHESIS</span>
                    </div>
                    <p className="font-sans text-body-sm text-amber-100/90 leading-relaxed">
                      {topic.explanatory_synthesis}
                    </p>
                  </div>
                )}

                {/* 2 Columns: Executive Summary & Action Items/Sources */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-space-md">
                  {/* Summary */}
                  <div className="bg-[#121419] border border-surface-container-highest rounded-xl p-5 flex flex-col justify-between">
                    <div>
                      <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-4 font-bold">
                        EXECUTIVE SUMMARY & INSIGHTS
                      </div>
                      <div className="font-sans text-body-sm text-secondary leading-relaxed space-y-2.5">
                        {topic.executive_summary?.map((sum, i) => (
                          <div key={i} className="flex items-start gap-2.5 text-primary">
                            <span className="text-amber-400 select-none">▪</span>
                            <span>{sum}</span>
                          </div>
                        )) || <div>No summary available</div>}
                      </div>
                    </div>
                  </div>

                  {/* Actions & Citations */}
                  <div className="bg-[#121419] border border-surface-container-highest rounded-xl p-5 flex flex-col justify-between">
                    <div>
                      <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-4 font-bold">
                        ACTION ITEMS & CITATIONS
                      </div>

                      {topic.action_items && topic.action_items.length > 0 && (
                        <div className="mb-4">
                          <strong className="text-primary font-mono text-[9px] tracking-widest uppercase mb-2 block">
                            Key Action Items
                          </strong>
                          <div className="space-y-1.5">
                            {topic.action_items.map((act, i) => (
                              <div key={i} className="flex items-start gap-2 text-body-xs font-sans text-primary">
                                <span className="text-emerald-400">✓</span>
                                <span>{act}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {topic.web_sources && topic.web_sources.length > 0 && (
                        <div>
                          <strong className="text-primary font-mono text-[9px] tracking-widest uppercase mb-2 block">
                            Corroborating Citations
                          </strong>
                          <div className="space-y-1">
                            {topic.web_sources.slice(0, 3).map((src, i) => (
                              <a
                                key={i}
                                href={src}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="block text-amber-200/90 hover:text-amber-300 font-mono text-[10px] truncate hover:underline"
                                title={src}
                              >
                                🔗 {src}
                              </a>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
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
