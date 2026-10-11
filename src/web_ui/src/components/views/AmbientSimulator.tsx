import React, { useState } from "react";
import { ScreenHeader } from "../ui/ScreenHeader";
import { StatusBadge } from "../ui/StatusBadge";
import { playAcousticVerificationTone } from "@/utils/audioEffects";

interface AmbientSimulatorProps {
  simText: string;
  setSimText: (text: string) => void;
  simRunning: boolean;
  runSimulation: () => void;
  simResult: any;
}

export function AmbientSimulator({
  simText,
  setSimText,
  simRunning,
  runSimulation,
  simResult,
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
      title: "Social Networking & Promises",
      desc: "Simulates dialogue meeting Andrea from Almaviva, extracting contact commitments & follow-up.",
      badge: "CONTACT_ROLODEX",
      icon: "🤝",
      text: "Hi! I'm Andrea Valenti, DevOps Lead at Almaviva. Great to meet you at AWS re:Invent. I will send you the fastmcp schema on Slack by Thursday.",
    },
    {
      id: "03",
      title: "Ambient Voice Task Scheduler",
      desc: "Passively extracts a scheduled reminder to inspect an appliance later in the day.",
      badge: "AMBIENT_SCHEDULER",
      icon: "⏱️",
      text: "Remind me to check the garage freezer and seal the basement window at 6:30 PM.",
    },
    {
      id: "04",
      title: "AWS Bedrock AgentCore Tech",
      desc: "Engineering deep-dive on Bedrock Mantle and FastMCP architecture, drafting synthetic topic notes.",
      badge: "TOPIC_DOSSIER",
      icon: "📚",
      text: "We spent the morning discussing how to route FastMCP streams directly into Bedrock AgentCore. The main action item is for Sarah to test the latency overhead.",
    },
    {
      id: "05",
      title: "Casual Banter (Drop >90%)",
      desc: "Small talk concerning drizzle; verifies PII scrubber drops low-entropy ephemeral small talk.",
      badge: "NOOP_DROP_FILTER",
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

  const extractedActions = simResult?.result?.actions || simResult?.result?.state?.identified_actions || [];
  const extractedSocial = simResult?.result?.social || simResult?.result?.state?.social_observations || [];
  const extractedTopics = simResult?.result?.topics || simResult?.result?.state?.topic_briefings || [];

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
          <div className="bg-[#121419] border border-surface-container-highest rounded-xl p-4 font-mono w-[280px]">
            <div className="text-[9px] text-secondary tracking-[0.2em] uppercase mb-1">
              INSPECTION CADENCE
            </div>
            <div className="text-[14px] text-emerald-400 font-bold tracking-wider mb-1">
              REALTIME ZERO-LAG
            </div>
            <div className="text-[9px] text-secondary tracking-[0.2em] uppercase">
              BUFFER: 2048 SAMPLES
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
                className="text-secondary hover:text-primary font-mono text-[10px] tracking-widest uppercase"
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
                    className={`px-3 py-1 rounded font-mono text-[9px] uppercase tracking-wider ${
                      activeResultTab === "parsed" ? "bg-primary text-background font-bold" : "text-secondary"
                    }`}
                  >
                    Summary
                  </button>
                  <button
                    onClick={() => setActiveResultTab("raw")}
                    className={`px-3 py-1 rounded font-mono text-[9px] uppercase tracking-wider ${
                      activeResultTab === "raw" ? "bg-primary text-background font-bold" : "text-secondary"
                    }`}
                  >
                    Raw JSON
                  </button>
                </div>
              </div>

              {simResult ? (
                activeResultTab === "parsed" ? (
                  <div className="space-y-4 max-h-[300px] overflow-y-auto">
                    <div className="font-mono text-[9px] text-emerald-400 tracking-widest uppercase">
                      ✅ Pipeline completed in {simResult.elapsed_seconds || "0.4"}s
                    </div>

                    {extractedActions.length > 0 && (
                      <div className="bg-[#121419] p-3 rounded-xl border border-white/5">
                        <div className="font-mono text-[9px] text-amber-400 uppercase font-bold mb-1">
                          Extracted Actions ({extractedActions.length})
                        </div>
                        {extractedActions.map((a: any, i: number) => (
                          <div key={i} className="text-xs text-primary font-sans">
                            • {a.action_type || a.raw_statement} ({(a.confidence * 100).toFixed(0)}%)
                          </div>
                        ))}
                      </div>
                    )}

                    {extractedSocial.length > 0 && (
                      <div className="bg-[#121419] p-3 rounded-xl border border-white/5">
                        <div className="font-mono text-[9px] text-cyan-400 uppercase font-bold mb-1">
                          Extracted Social ({extractedSocial.length})
                        </div>
                        {extractedSocial.map((s: any, i: number) => (
                          <div key={i} className="text-xs text-primary font-sans">
                            • {s.person_name || s.name} ({s.company_or_role || "Contact"})
                          </div>
                        ))}
                      </div>
                    )}

                    {extractedTopics.length > 0 && (
                      <div className="bg-[#121419] p-3 rounded-xl border border-white/5">
                        <div className="font-mono text-[9px] text-purple-400 uppercase font-bold mb-1">
                          Extracted Topic Dossier ({extractedTopics.length})
                        </div>
                        {extractedTopics.map((t: any, i: number) => (
                          <div key={i} className="text-xs text-primary font-sans">
                            • {t.topic_title}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <pre className="p-4 bg-[#0a0b0e] border border-white/5 rounded-xl font-mono text-[10px] text-emerald-300 max-h-[300px] overflow-y-auto whitespace-pre-wrap">
                    {JSON.stringify(simResult, null, 2)}
                  </pre>
                )
              ) : (
                <div className="py-12 text-center text-secondary font-mono text-xs">
                  {simRunning ? "Executing LangGraph pipeline..." : "Run a simulation above to view live execution telemetry."}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
