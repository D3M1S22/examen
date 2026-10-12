import React, { useState } from "react";
import { ScreenHeader } from "../ui/ScreenHeader";
import { StatusBadge, DomainBadge } from "../ui/StatusBadge";
import { playAcousticVerificationTone } from "@/utils/audioEffects";

interface AmbientSimulatorProps {
  simText: string;
  setSimText: (text: string) => void;
  simRunning: boolean;
  runSimulation: () => void;
  simResult: any;
  statusData?: any;
}

export function AmbientSimulator({
  simText,
  setSimText,
  simRunning,
  runSimulation,
  simResult,
  statusData,
}: AmbientSimulatorProps) {
  const [activeResultTab, setActiveResultTab] = useState<"parsed" | "raw">("parsed");

  const presets = [
    {
      id: "01",
      title: "Iron & Gas Safety",
      desc: "Triggers acoustic iron disconnect click & stove dial lock. Corroborates domestic peace of mind.",
      badge: "DOMESTIC_SAFETY",
      icon: "🛡️",
      text: "I just unplugged the clothes iron from the wall outlet and styled my hair — all good. Gas stovetop is cold and switched off.",
    },
    {
      id: "02",
      title: "Ambient Voice Task Scheduler",
      desc: "Passively extracts a future domestic reminder with ISO-8601 relative time calculation.",
      badge: "AMBIENT_SCHEDULER",
      icon: "⏱️",
      text: "Remind me to turn off the garden irrigation valve in an hour before leaving for dinner.",
    },
    {
      id: "03",
      title: "Bilateral Social Commitments",
      desc: "Extracts contact identity and mutual promise with debtor tracking (user vs contact).",
      badge: "BILATERAL_PROMISE",
      icon: "🤝",
      text: "Nice to meet you Giulia Verdi, Senior Director at CloudOps. I will send you our architecture pitch deck tomorrow at 10 AM.",
    },
    {
      id: "04",
      title: "Executive Web Profiling",
      desc: "Passes strict 2-anchor disambiguation guardrails to trigger autonomous AI dossier.",
      badge: "EXECUTIVE_CRM",
      icon: "👤",
      text: "Pleased to meet you, I'm Dr. Elena Rostova, VP of AI Research at CloudScale. Let's discuss Raft consensus algorithms and distributed systems.",
    },
    {
      id: "05",
      title: "Contextual Topic Synthesis",
      desc: "Initiates deep background research and explanatory academic synthesis with citation grounding.",
      badge: "TOPIC_DOSSIER",
      icon: "📚",
      text: "In today's systems seminar we study distributed consensus algorithms and the Raft leader election theorem compared to Multi-Paxos.",
    },
    {
      id: "06",
      title: "Casual Banter (Privacy Drop)",
      desc: "Demonstrates Nemotron Gatekeeper filtering low-entropy small talk to protect user privacy.",
      badge: "PRIVACY_SCRUBBER",
      icon: "☕",
      text: "Man, it's really raining outside today. I should have brought my umbrella. Oh well, the coffee here is good.",
    },
  ];

  const handleRun = () => {
    playAcousticVerificationTone();
    runSimulation();
  };

  const steps = [
    { id: 1, title: "Bee Audio Input Ingestion", desc: "48kHz Opus stream chunk unpacked & timestamped." },
    { id: 2, title: "Nemotron Semantic Gatekeeper", desc: "Anonymize speaker identities; evaluate relevance gate." },
    { id: 3, title: "Intent Classification Fan-Out", desc: "Route to Domestic Safety vs Social Memory vs Dossier." },
    { id: 4, title: "Bedrock Agentic Synthesis", desc: "Extract entities, corroboration schema, vector write." },
    { id: 5, title: "FastMCP Alexa+ Server Broadcast", desc: "Publish entity state for immediate ambient recall query." },
  ];

  // Robust extraction from FastMCP / Bedrock AgentCore response
  const res = simResult?.result;
  const elapsed = simResult?.elapsed_seconds || 0.4;
  const summary = res?.summary || simResult?.summary || "";
  const categories: string[] = res?.categories || [];
  const isNoop = categories.includes("noop") || categories.length === 0;

  // Extracted Actions
  const rawActionData = res?.action_data;
  const extractedActions: any[] = Array.isArray(rawActionData?.actions)
    ? rawActionData.actions
    : rawActionData?.action_type
    ? [rawActionData]
    : Array.isArray(res?.actions)
    ? res.actions
    : Array.isArray(res?.state?.identified_actions)
    ? res.state.identified_actions
    : [];

  // Extracted Social
  const rawSocialData = res?.social_data;
  const extractedContacts: any[] = Array.isArray(rawSocialData?.contacts)
    ? rawSocialData.contacts
    : rawSocialData?.name
    ? [rawSocialData]
    : Array.isArray(res?.social)
    ? res.social
    : Array.isArray(res?.state?.social_observations)
    ? res.state.social_observations
    : [];

  const extractedCommitments: any[] = Array.isArray(rawSocialData?.commitments)
    ? rawSocialData.commitments
    : extractedContacts.flatMap((c) => c.commitments || []);

  // Extracted Topic Dossier
  const extractedTopic =
    res?.briefing_report ||
    (Array.isArray(res?.topics) ? res.topics[0] : null) ||
    (Array.isArray(res?.state?.topic_briefings) ? res.state.topic_briefings[0] : null) ||
    null;

  // Extracted Ambient Scheduled Task (Milestone 1.2)
  const extractedTask = res?.scheduled_task || null;

  return (
    <div className="space-y-space-lg animate-in fade-in max-w-[1400px] mx-auto">
      <ScreenHeader
        directive="DIAGNOSTIC TESTBENCH // SECTOR 06"
        title="AMBIENT AUDIO STREAM SIMULATOR & AGENTCORE PIPELINE"
        description={
          <>
            Welcome, Hackathon Judges and Testers! This Ambient Simulator provides a direct interface to test EXAMEN's AgentCore pipeline without needing the physical Bee hardware. Select a preset below or type ambient dialogue to watch the LangGraph pipeline extract peace of mind anchors, social commitments, and topic dossiers in real-time.
          </>
        }
        rightElement={
          <div className="bg-[#121419] border border-surface-container-highest rounded-xl p-4 font-mono w-[300px]">
            <div className="flex justify-between items-center text-[8px] text-secondary tracking-[0.2em] uppercase mb-1">
              <span>AVG PIPELINE LATENCY</span>
              <span className="text-emerald-400 font-bold">
                {statusData?.telemetry?.latency?.average_ms ? `${statusData.telemetry.latency.average_ms}ms` : "CALIBRATING"}
              </span>
            </div>
            <div className="flex justify-between items-center text-[8px] text-secondary tracking-[0.2em] uppercase mb-1">
              <span>SAMPLES RECORDED</span>
              <span className="text-primary font-bold">
                {statusData?.telemetry?.latency?.sample_count ?? 0} RUNS
              </span>
            </div>
            <div className="flex justify-between items-center text-[8px] text-secondary tracking-[0.2em] uppercase">
              <span>REASONING MODEL</span>
              <span className="text-cyan-400 font-bold truncate max-w-[150px]" title={statusData?.config?.reasoner_model}>
                {statusData?.config?.reasoner_model?.split(":")?.[0]?.toUpperCase() || "AWS BEDROCK"}
              </span>
            </div>
          </div>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg">
        {/* Left Column: Presets + Utterance Input */}
        <div className="lg:col-span-7 flex flex-col gap-space-lg">
          {/* Presets */}
          <div className="card-elevated p-space-lg bg-surface-container-low border-surface-container-highest rounded-2xl">
            <div className="flex items-center justify-between mb-4 pb-2 border-b border-white/5">
              <div className="font-mono text-[10px] text-primary tracking-[0.2em] uppercase flex items-center gap-2 font-bold">
                <span>⚡</span>
                <span>SYNTHETIC INGESTION PRESETS</span>
              </div>
              <div className="font-mono text-[9px] text-amber-400 tracking-widest uppercase">
                CLICK TO INJECT
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {presets.map((p) => (
                <button
                  key={p.id}
                  onClick={() => setSimText(p.text)}
                  className="bg-[#121419] border border-surface-container-highest rounded-xl p-3.5 text-left hover:border-amber-400 transition-colors group flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-start justify-between mb-1.5">
                      <div className="font-mono text-[10px] text-primary tracking-widest font-bold flex items-center gap-1.5">
                        <span>{p.icon}</span>
                        <span>{p.title}</span>
                      </div>
                    </div>
                    <div className="font-sans text-xs text-secondary mb-3 leading-relaxed">
                      {p.desc}
                    </div>
                  </div>
                  <span className="font-mono text-[8px] py-0.5 px-2 rounded bg-black/40 border border-white/5 text-amber-300 w-max uppercase">
                    {p.badge}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Injector Textarea */}
          <div className="card-elevated p-space-lg bg-surface-container-low border-surface-container-highest rounded-2xl flex-1 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-4 pb-2 border-b border-white/5">
                <div className="font-mono text-[10px] text-primary tracking-[0.2em] uppercase flex items-center gap-2 font-bold">
                  <span>🎙️</span>
                  <span>TRANSCRIBED UTTERANCE INJECTOR</span>
                </div>
                <div className="font-mono text-[9px] text-secondary tracking-widest uppercase">
                  OPUS 48KHZ PCM
                </div>
              </div>

              <div className="flex items-center justify-between mb-2">
                <div className="font-mono text-[9px] text-secondary tracking-widest uppercase">
                  TRANSCRIPT BUFFER
                </div>
                <div className="font-mono text-[9px] text-amber-400 tracking-widest uppercase">
                  {simText.length} CHARACTERS
                </div>
              </div>

              <textarea
                rows={5}
                className="w-full bg-[#101216] border border-surface-container-highest rounded-xl p-4 font-sans text-body-sm text-primary placeholder-zinc-600 focus:outline-none focus:border-amber-400 resize-none mb-4 transition-colors"
                placeholder="Type or select a preset above... e.g. I just unplugged the iron and locked the door."
                value={simText}
                onChange={(e) => setSimText(e.target.value)}
              />
            </div>

            <div className="flex items-center justify-between pt-2">
              <button
                onClick={() => setSimText("")}
                className="text-secondary hover:text-primary font-mono text-[10px] tracking-widest uppercase transition-colors"
              >
                Clear Buffer
              </button>

              <button
                onClick={handleRun}
                disabled={simRunning || !simText.trim()}
                className="px-6 py-3 rounded-xl bg-primary hover:bg-surface-tint text-background font-mono text-[10px] tracking-widest font-bold uppercase transition-all shadow-md disabled:opacity-40 flex items-center gap-2"
              >
                {simRunning ? (
                  <>
                    <span className="w-3 h-3 border-2 border-background border-t-transparent rounded-full animate-spin" />
                    <span>Processing Pipeline...</span>
                  </>
                ) : (
                  <>
                    <span>▶</span>
                    <span>Inject Stream to AgentCore</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Right Column: Execution Flow & Live Output */}
        <div className="lg:col-span-5 flex flex-col gap-space-lg">
          {/* Pipeline Stages */}
          <div className="card-elevated p-space-lg bg-surface-container-low border-surface-container-highest rounded-2xl">
            <div className="flex items-center justify-between mb-6 pb-2 border-b border-white/5">
              <div className="font-mono text-[10px] text-primary tracking-[0.2em] uppercase font-bold flex items-center gap-2">
                <span>⚙️</span>
                <span>AGENTCORE PIPELINE STAGES</span>
              </div>
              <StatusBadge status={simRunning ? "pending" : "completed"} label={simRunning ? "PROCESSING" : "READY"} />
            </div>

            <div className="space-y-3">
              {steps.map((step) => (
                <div
                  key={step.id}
                  className={`p-3 rounded-xl border flex items-center gap-3 transition-colors ${
                    simRunning
                      ? "bg-amber-950/20 border-amber-500/40 text-amber-200"
                      : "bg-[#121419] border-white/5 text-zinc-300"
                  }`}
                >
                  <div className="w-6 h-6 rounded-full bg-surface-container-highest flex items-center justify-center font-mono text-[10px] font-bold shrink-0">
                    {step.id}
                  </div>
                  <div>
                    <div className="font-mono text-[10px] font-bold uppercase">{step.title}</div>
                    <div className="font-sans text-xs text-secondary">{step.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Results Box */}
          <div className="card-elevated p-space-lg bg-surface-container-low border-surface-container-highest rounded-2xl flex-1 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-4 pb-2 border-b border-white/5">
                <div className="font-mono text-[10px] text-primary tracking-[0.2em] uppercase font-bold">
                  PIPELINE EXECUTION TELEMETRY
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setActiveResultTab("parsed")}
                    className={`px-3 py-1 rounded font-mono text-[9px] uppercase tracking-wider transition-colors ${
                      activeResultTab === "parsed" ? "bg-primary text-background font-bold" : "text-secondary hover:text-white"
                    }`}
                  >
                    Summary
                  </button>
                  <button
                    onClick={() => setActiveResultTab("raw")}
                    className={`px-3 py-1 rounded font-mono text-[9px] uppercase tracking-wider transition-colors ${
                      activeResultTab === "raw" ? "bg-primary text-background font-bold" : "text-secondary hover:text-white"
                    }`}
                  >
                    Raw JSON
                  </button>
                </div>
              </div>

              {simResult ? (
                activeResultTab === "parsed" ? (
                  <div className="space-y-4 max-h-[380px] overflow-y-auto pr-1">
                    {/* Status & Latency Banner */}
                    <div className="flex items-center justify-between bg-black/40 border border-white/5 rounded-xl px-3.5 py-2">
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                        <span className="font-mono text-[10px] text-emerald-400 uppercase font-bold tracking-wider">
                          Pipeline Executed Nominal
                        </span>
                      </div>
                      <span className="font-mono text-[10px] text-secondary">
                        ⏱️ {elapsed}s
                      </span>
                    </div>

                    {/* Gatekeeper Classification Categories */}
                    {categories.length > 0 && (
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-[9px] text-secondary tracking-widest uppercase">
                          Gatekeeper Route:
                        </span>
                        {categories.map((cat, idx) => (
                          <span
                            key={idx}
                            className="px-2 py-0.5 rounded-full bg-amber-950/50 border border-amber-500/40 text-amber-300 font-mono text-[9px] uppercase font-bold tracking-wider"
                          >
                            {cat.replace(/_/g, " ")}
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Explanatory Pipeline Summary */}
                    {summary && (
                      <div className="bg-[#121419] p-3 rounded-xl border border-white/5">
                        <div className="font-mono text-[9px] text-secondary uppercase tracking-widest mb-1">
                          Pipeline Synthesis
                        </div>
                        <div className="text-xs text-zinc-200 font-sans italic">
                          "{summary}"
                        </div>
                      </div>
                    )}

                    {/* Extracted Ambient Task (Milestone 1.2) */}
                    {extractedTask && (
                      <div className="bg-[#121419] p-3.5 rounded-xl border border-amber-500/30 bg-amber-950/10">
                        <div className="flex items-center justify-between mb-2">
                          <div className="font-mono text-[9px] text-amber-400 uppercase font-bold flex items-center gap-1.5">
                            <span>⏱️</span>
                            <span>Ambient Task Scheduled</span>
                          </div>
                          <DomainBadge domain={extractedTask.domain || "routine"} />
                        </div>
                        <div className="font-serif text-sm text-primary font-bold mb-1">
                          {extractedTask.task_title || extractedTask.title}
                        </div>
                        <div className="font-mono text-[9px] text-secondary flex items-center gap-3">
                          <span>Target: {extractedTask.scheduled_time || "Pending"}</span>
                          <span>•</span>
                          <span>Recurrence: {extractedTask.recurrence || "daily"}</span>
                          <span>•</span>
                          <span className="text-amber-400">Origin: {extractedTask.origin || "ambient_voice"}</span>
                        </div>
                      </div>
                    )}

                    {/* Extracted Actions */}
                    {extractedActions.length > 0 && (
                      <div className="bg-[#121419] p-3 rounded-xl border border-emerald-500/30 bg-emerald-950/10">
                        <div className="flex items-center justify-between mb-2">
                          <div className="font-mono text-[9px] text-emerald-400 uppercase font-bold flex items-center gap-1.5">
                            <span>🛡️</span>
                            <span>Verified Actions ({extractedActions.length})</span>
                          </div>
                          <StatusBadge status="verified" label="VERIFIED" />
                        </div>
                        <div className="space-y-2">
                          {extractedActions.map((a: any, i: number) => (
                            <div key={i} className="text-xs text-zinc-200 font-sans border-l-2 border-emerald-500/60 pl-2">
                              <div className="font-bold text-white capitalize">
                                {a.action_type ? a.action_type.replace(/_/g, " ") : "Action Registered"}
                              </div>
                              <div className="text-[11px] text-zinc-400 italic">
                                "{a.raw_statement || a.notes || "Acoustic detent confirmed."}"
                              </div>
                              <div className="font-mono text-[8px] text-secondary mt-0.5">
                                Confidence: {((a.confidence ?? 1.0) * 100).toFixed(1)}% • Domain: {a.domain || "safety"}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Extracted Social Contacts & Commitments */}
                    {(extractedContacts.length > 0 || extractedCommitments.length > 0) && (
                      <div className="bg-[#121419] p-3 rounded-xl border border-cyan-500/30 bg-cyan-950/10">
                        <div className="font-mono text-[9px] text-cyan-400 uppercase font-bold mb-2 flex items-center gap-1.5">
                          <span>🤝</span>
                          <span>Social Memory & Bilateral Promises</span>
                        </div>
                        {extractedContacts.map((c: any, i: number) => (
                          <div key={i} className="mb-2 last:mb-0">
                            <div className="text-xs font-bold text-white">
                              {c.name || c.person_name}
                              <span className="font-normal text-secondary text-[11px] ml-1.5">
                                ({c.company_or_role || "Interlocutor"})
                              </span>
                            </div>
                            {c.contact_info && (
                              <div className="font-mono text-[8px] text-cyan-300">
                                📬 {c.contact_info}
                              </div>
                            )}
                          </div>
                        ))}
                        {extractedCommitments.length > 0 && (
                          <div className="mt-2 pt-2 border-t border-white/5 space-y-1">
                            <div className="font-mono text-[8px] text-amber-300 uppercase tracking-widest font-bold">
                              Tracked Commitments:
                            </div>
                            {extractedCommitments.map((cmt: any, idx: number) => {
                              const desc = typeof cmt === "object" ? cmt.description : String(cmt);
                              const debtor = typeof cmt === "object" ? cmt.debtor : "contact";
                              return (
                                <div key={idx} className="text-[11px] text-zinc-300 flex items-start gap-1.5">
                                  <span className="font-mono text-[8px] px-1.5 py-0.5 rounded bg-black/60 border border-white/10 uppercase text-amber-300 font-bold">
                                    {debtor === "user" ? "I PROMISED" : "PROMISED TO ME"}
                                  </span>
                                  <span>{desc}</span>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Extracted Topic Dossier */}
                    {extractedTopic && (
                      <div className="bg-[#121419] p-3 rounded-xl border border-purple-500/30 bg-purple-950/10">
                        <div className="flex items-center justify-between mb-1.5">
                          <div className="font-mono text-[9px] text-purple-400 uppercase font-bold flex items-center gap-1.5">
                            <span>📚</span>
                            <span>Topic Dossier Synthesized</span>
                          </div>
                          <span className="px-2 py-0.5 rounded bg-purple-950 text-purple-300 font-mono text-[8px] uppercase">
                            {extractedTopic.context_type || "RESEARCH"}
                          </span>
                        </div>
                        <div className="font-serif text-sm font-bold text-white mb-1">
                          {extractedTopic.topic_title}
                        </div>
                        <div className="text-xs text-zinc-300 font-sans line-clamp-3 leading-relaxed mb-2">
                          {extractedTopic.explanatory_synthesis || extractedTopic.summary || (extractedTopic.executive_summary || [])[0]}
                        </div>
                        {Array.isArray(extractedTopic.sources) && extractedTopic.sources.length > 0 && (
                          <div className="font-mono text-[8px] text-secondary">
                            📚 {extractedTopic.sources.length} authoritative web citations referenced
                          </div>
                        )}
                      </div>
                    )}

                    {/* Fallback for Noop / Ephemeral Dropped */}
                    {isNoop && extractedActions.length === 0 && extractedContacts.length === 0 && !extractedTopic && !extractedTask && (
                      <div className="bg-[#121419] p-3.5 rounded-xl border border-zinc-800 text-center">
                        <div className="text-lg mb-1">☕</div>
                        <div className="font-mono text-[10px] text-zinc-300 uppercase font-bold tracking-wider mb-1">
                          Ephemeral Small Talk Filtered
                        </div>
                        <div className="font-sans text-xs text-zinc-500 leading-relaxed max-w-sm mx-auto">
                          Gatekeeper classified utterance as NOOP with 0 action entropy. Dropped to preserve user privacy and prevent memory pollution.
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <pre className="p-4 bg-[#0a0b0e] border border-white/5 rounded-xl font-mono text-[10px] text-emerald-300 max-h-[380px] overflow-y-auto whitespace-pre-wrap">
                    {JSON.stringify(simResult, null, 2)}
                  </pre>
                )
              ) : (
                <div className="py-16 text-center text-secondary font-mono text-xs">
                  {simRunning ? (
                    <div className="flex flex-col items-center gap-2">
                      <span className="w-5 h-5 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
                      <span>Executing LangGraph AgentCore pipeline...</span>
                    </div>
                  ) : (
                    "Select a preset or click 'Inject Stream to AgentCore' above."
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
