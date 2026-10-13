import React, { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import useSWR from "swr";
import { EchoShowCardResponse } from "@/types/schemas";
import { speakAlexaReassurance } from "@/utils/audioEffects";
import { getApiBaseUrl } from "@/utils/api";

interface EchoShowModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialTemplate?: string;
}

const fetcher = (url: string) => fetch(`${getApiBaseUrl()}${url}`).then((res) => res.json());

export function EchoShowModal({
  isOpen,
  onClose,
  initialTemplate = "DEEP_BRIEFING_VIEWER",
}: EchoShowModalProps) {
  const [mounted, setMounted] = useState(false);
  const [template, setTemplate] = useState(initialTemplate);
  const [echoTime, setEchoTime] = useState("");

  useEffect(() => {
    setMounted(true);
  }, []);

  const { data: cardData, isLoading } = useSWR<EchoShowCardResponse>(
    isOpen ? `/api/cards/preview?template=${template}` : null,
    fetcher
  );

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
      const updateClock = () => {
        const now = new Date();
        setEchoTime(
          `${now.getHours().toString().padStart(2, "0")}:${now
            .getMinutes()
            .toString()
            .padStart(2, "0")}`
        );
      };
      updateClock();
      const interval = setInterval(updateClock, 1000);

      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === "Escape") onClose();
      };
      window.addEventListener("keydown", handleKeyDown);

      return () => {
        document.body.style.overflow = "unset";
        clearInterval(interval);
        window.removeEventListener("keydown", handleKeyDown);
      };
    } else {
      document.body.style.overflow = "unset";
    }
  }, [isOpen, onClose]);

  if (!isOpen || !mounted) return null;

  const payload = (cardData as any)?.card_payload || cardData || {};

  const cardTitle =
    cardData?.title ||
    payload.title ||
    cardData?.topic_title ||
    payload.topic_title ||
    (template === "DEEP_BRIEFING_VIEWER" ? "Autonomous Topic Research Dossier" :
     template === "SOCIAL_PROFILE_CARD" ? "Executive Social Rolodex Dossier" :
     template === "SOCIAL_COMMITMENTS_CARD" ? "Bilateral Social Commitments" :
     template === "ACTION_VERIFIED_BADGE" ? "Peace of Mind Acoustic Corroboration" :
     template === "DAILY_ACTIONS_RECAP" ? "Daily Verification Recap" :
     template === "UPCOMING_TASKS_VIEWER" ? "Upcoming Monitored Routines" :
     template === "SESSION_DOSSIER_VIEWER" ? "Macro Session Intelligence Dossier" : "Multimodal Echo Show Card");

  const badgeText =
    cardData?.header_badge ||
    cardData?.ui_card_type ||
    cardData?.display_template ||
    payload.template ||
    template.replace(/_/g, " ");

  const spokenText =
    cardData?.spoken_summary ||
    payload.spoken_summary ||
    cardData?.voice_summary ||
    payload.voice_summary ||
    `Displaying ${cardTitle}. All background telemetry is nominal.`;

  const synthesis =
    payload.explanatory_synthesis ||
    payload.synthesis ||
    cardData?.explanatory_synthesis ||
    cardData?.display_data?.explanatory_synthesis;

  const summaryText =
    payload.bio_summary ||
    payload.bio ||
    payload.summary ||
    cardData?.display_data?.summary ||
    (cardData as any)?.web_profile?.bio_summary;

  const bullets =
    payload.bullets ||
    payload.executive_summary ||
    cardData?.executive_summary ||
    cardData?.display_data?.facts ||
    [];

  const sources =
    payload.sources ||
    payload.web_sources ||
    cardData?.web_sources ||
    [];

  const actionItems =
    payload.action_items ||
    cardData?.action_items ||
    [];

  const commitmentsList =
    payload.commitments ||
    cardData?.commitments ||
    cardData?.display_data?.commitments ||
    [];

  const actionsList =
    payload.actions ||
    cardData?.actions ||
    cardData?.display_data?.items ||
    [];

  const tasksList =
    payload.tasks ||
    cardData?.tasks ||
    [];

  const contactObj = cardData?.contact || payload.contact;
  const webProfileObj = cardData?.web_profile || payload.web_profile;

  const handleSpeakCard = () => {
    speakAlexaReassurance(spokenText);
  };

  const templates = [
    { id: "DEEP_BRIEFING_VIEWER", label: "📚 Deep Briefing" },
    { id: "SOCIAL_PROFILE_CARD", label: "👤 Social Profile" },
    { id: "SOCIAL_COMMITMENTS_CARD", label: "🤝 Commitments" },
    { id: "ACTION_VERIFIED_BADGE", label: "🛡️ Peace of Mind" },
    { id: "DAILY_ACTIONS_RECAP", label: "📋 Daily Recap" },
    { id: "UPCOMING_TASKS_VIEWER", label: "⏱️ Upcoming Tasks" },
    { id: "SESSION_DOSSIER_VIEWER", label: "🏛️ Session Dossier" },
  ];

  return createPortal(
    <div
      className="fixed inset-0 z-[9999] overflow-y-auto bg-black/90 backdrop-blur-md flex items-center justify-center p-3 sm:p-6"
      onClick={onClose}
      aria-modal="true"
      role="dialog"
    >
      <div
        className="relative w-full max-w-4xl my-auto animate-in fade-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Device Frame Top Label */}
        <div className="flex items-center justify-between px-2 mb-2">
          <div className="font-mono text-[10px] text-zinc-400 tracking-[0.2em] uppercase flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
            AMAZON ECHO SHOW 15 MULTIMODAL SIMULATOR // EXT-APP RUNTIME
          </div>
          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-white font-mono text-[11px] tracking-wider uppercase px-2.5 py-1 rounded bg-zinc-800/80 hover:bg-zinc-700 transition-colors"
          >
            ✕ Exit Echo View
          </button>
        </div>

        {/* Physical Hardware Bezel */}
        <div className="bg-[#101216] border-4 border-[#242833] rounded-3xl p-4 sm:p-6 shadow-[0_25px_60px_-15px_rgba(0,0,0,0.9)] relative">
          {/* Echo Camera Notch */}
          <div className="absolute top-2 left-1/2 -translate-x-1/2 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#0a0b0d] border border-white/10"></span>
            <span className="w-1.5 h-1.5 rounded-full bg-red-900/30"></span>
          </div>

          {/* Glass Display Screen */}
          <div className="bg-[#08090b] border border-white/5 rounded-2xl overflow-hidden min-h-[540px] flex flex-col relative text-zinc-100">
            {/* Echo System Bar */}
            <div className="bg-black/60 px-6 py-3 flex items-center justify-between border-b border-white/5">
              <div className="font-mono text-base font-bold text-white tracking-wider">
                {echoTime || "12:00"}
              </div>

              <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-950/60 border border-cyan-500/40 text-cyan-300 font-mono text-[10px] tracking-widest uppercase">
                <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
                <span>Alexa+ Ambient Ext-App</span>
              </div>

              <div className="flex items-center gap-3 text-zinc-400 text-xs font-mono">
                <span>📶 5G MESH</span>
                <span className="opacity-40">•</span>
                <span>BEE LINKED</span>
              </div>
            </div>

            {/* Template Switcher Bar */}
            <div className="bg-[#121419] px-4 py-2 border-b border-white/5 flex items-center gap-2 overflow-x-auto hide-scrollbar">
              {templates.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setTemplate(t.id)}
                  className={`px-3 py-1.5 rounded-lg font-mono text-[10px] tracking-wider whitespace-nowrap transition-all uppercase ${
                    template === t.id
                      ? "bg-cyan-500 text-black font-bold shadow-md"
                      : "text-zinc-400 hover:text-white hover:bg-white/5"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {/* Dynamic Echo Show Card Canvas */}
            <div className="p-6 sm:p-8 flex-1 flex flex-col justify-between">
              {isLoading ? (
                <div className="flex-1 flex flex-col items-center justify-center gap-3 py-16">
                  <div className="w-8 h-8 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin" />
                  <div className="font-mono text-[10px] text-zinc-400 tracking-widest uppercase">
                    Rendering Echo Show Multimodal Card...
                  </div>
                </div>
              ) : cardData ? (
                <div className="space-y-6 flex-1 flex flex-col justify-between">
                  {/* Card Header */}
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <span className="px-2.5 py-0.5 rounded bg-cyan-950/70 text-cyan-300 border border-cyan-500/30 font-mono text-[9px] tracking-widest uppercase font-bold">
                          {badgeText}
                        </span>
                        <span className="font-mono text-[9px] text-zinc-500 tracking-widest uppercase">
                          {cardData.timestamp ? cardData.timestamp.replace("T", " ").substring(0, 19) : "LIVE"}
                        </span>
                      </div>
                      <button
                        onClick={handleSpeakCard}
                        className="px-3.5 py-1.5 rounded-full bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-400/40 text-cyan-300 font-mono text-[10px] tracking-widest uppercase flex items-center gap-1.5 transition-colors font-bold shadow-sm"
                      >
                        <span>🔊</span>
                        <span>Read Aloud</span>
                      </button>
                    </div>

                    <h1 className="font-serif text-[30px] sm:text-[36px] text-white leading-tight mb-4">
                      {cardTitle}
                    </h1>

                    {/* Card Body Data */}
                    <div className="bg-[#12141a] border border-white/5 rounded-xl p-5 space-y-4">
                      {/* Explanatory synthesis */}
                      {synthesis && (
                        <div className="bg-amber-950/30 border border-amber-500/30 rounded-lg p-3 text-amber-200/90 font-sans text-body-sm leading-relaxed">
                          ⚡ <strong className="uppercase font-mono text-[10px] tracking-wider text-amber-300 mr-1">Thesis:</strong> {synthesis}
                        </div>
                      )}

                      {/* Event parts timeline (SESSION_DOSSIER_VIEWER) */}
                      {Array.isArray(payload.segments) && payload.segments.length > 0 && (
                        <div className="bg-black/30 border border-white/10 rounded-lg p-3 space-y-1.5">
                          <div className="font-mono text-[10px] tracking-wider text-cyan-300 uppercase flex items-center justify-between">
                            <span>🏛️ Event parts</span>
                            <span className="text-zinc-400">
                              {String(payload.status || "").toUpperCase()}
                              {payload.is_final === false ? " · PARTIAL BRIEFING" : ""}
                            </span>
                          </div>
                          {payload.segments.map((seg: any) => (
                            <div key={seg.index} className="flex items-center justify-between gap-3 text-sm">
                              <span className="text-zinc-200 truncate">
                                <span className="font-mono text-[10px] text-zinc-500 mr-2">{seg.index}</span>
                                {seg.title || (seg.status === "open" ? "Recording…" : "Awaiting synthesis")}
                              </span>
                              <span className="font-mono text-[10px] text-zinc-500 shrink-0">{seg.time_range}</span>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Summary / Bio */}
                      {summaryText && (
                        <div className="text-zinc-300 font-sans text-body-md leading-relaxed">
                          {summaryText}
                        </div>
                      )}

                      {/* Contact / Social Profile Card Details */}
                      {(contactObj || webProfileObj) && (
                        <div className="p-3 rounded-lg bg-black/40 border border-white/5 space-y-2">
                          <div className="text-cyan-300 font-serif text-lg">
                            {contactObj?.name || contactObj?.person_name || webProfileObj?.current_role || "Contact Information"}
                          </div>
                          {webProfileObj?.organization && (
                            <div className="text-xs text-zinc-400 font-mono uppercase tracking-wider">
                              Organization: {webProfileObj.organization}
                            </div>
                          )}
                          {webProfileObj?.areas_of_expertise && (
                            <div className="flex flex-wrap gap-1.5 pt-1">
                              {webProfileObj.areas_of_expertise.map((exp: string, i: number) => (
                                <span key={i} className="px-2 py-0.5 rounded bg-cyan-950/60 border border-cyan-500/20 text-cyan-300 font-mono text-[8px] uppercase">
                                  #{exp}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Facts / Bullets */}
                      {bullets.length > 0 && (
                        <ul className="space-y-2">
                          {bullets.map((f: string, i: number) => (
                            <li key={i} className="flex items-start gap-2.5 text-zinc-200 text-body-sm font-sans">
                              <span className="text-cyan-400 font-bold">•</span>
                              <span>{f}</span>
                            </li>
                          ))}
                        </ul>
                      )}

                      {/* Actions List (Daily recap or peace of mind) */}
                      {actionsList.length > 0 && (
                        <div className="space-y-2">
                          <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase">Verified Acoustic Actions:</div>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                            {actionsList.map((item: any, i: number) => (
                              <div key={i} className="p-3 rounded-lg bg-black/40 border border-white/5 flex items-center justify-between">
                                <span className="font-sans text-body-sm text-zinc-200 truncate pr-2">
                                  {item.title || item.action_type?.replace(/_/g, " ") || item.headline || item.raw_statement}
                                </span>
                                <span className="font-mono text-[9px] text-emerald-400 uppercase font-bold shrink-0">
                                  {item.status || "VERIFIED ✓"}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Tasks List */}
                      {tasksList.length > 0 && (
                        <div className="space-y-2">
                          <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase">Upcoming Monitored Routines:</div>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                            {tasksList.map((task: any, i: number) => (
                              <div key={i} className="p-3 rounded-lg bg-black/40 border border-white/5 flex items-center justify-between">
                                <span className="font-sans text-body-sm text-zinc-200 truncate pr-2">{task.title || task.headline}</span>
                                <span className="font-mono text-[9px] text-amber-400 uppercase font-bold shrink-0">{task.scheduled_time || task.status || "PENDING"}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Commitments List */}
                      {commitmentsList.length > 0 && (
                        <div className="space-y-2">
                          <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase">Bilateral Commitments:</div>
                          {commitmentsList.map((cmt: any, i: number) => {
                            const desc = typeof cmt === "object" ? cmt.description : String(cmt);
                            const debtor = typeof cmt === "object" ? cmt.debtor : "user";
                            return (
                              <div key={i} className="p-2.5 rounded bg-black/40 text-sm font-sans text-zinc-200 flex items-center gap-2.5">
                                <span>{debtor === "user" ? "📤" : "📥"}</span>
                                <span className="flex-1">{desc}</span>
                                <span className="font-mono text-[9px] text-cyan-400 uppercase">{debtor === "user" ? "You Promised" : "Contact"}</span>
                              </div>
                            );
                          })}
                        </div>
                      )}

                      {/* Citations / Sources */}
                      {sources.length > 0 && (
                        <div className="pt-2 border-t border-white/5">
                          <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase mb-1.5">Corroborating Web Sources:</div>
                          <div className="flex flex-wrap gap-2">
                            {sources.slice(0, 3).map((src: string, i: number) => (
                              <span key={i} className="text-amber-300 font-mono text-[10px] truncate max-w-xs">
                                🔗 {src}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Alexa Voice Speech Output Footer */}
                  <div className="mt-6 pt-4 border-t border-white/5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-full bg-cyan-500/20 border border-cyan-400/40 flex items-center justify-center text-cyan-300 shrink-0">
                        💬
                      </div>
                      <div>
                        <div className="font-mono text-[8px] text-zinc-400 tracking-widest uppercase">
                          Alexa Voice Output
                        </div>
                        <div className="font-sans text-xs text-zinc-200 italic max-w-lg">
                          "{spokenText}"
                        </div>
                      </div>
                    </div>

                    {/* Quick Alexa Prompts */}
                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={() => speakAlexaReassurance("Alexa says: Yes, your clothes iron is verified unplugged and cold.")}
                        className="px-3 py-1 rounded-full bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 font-mono text-[9px] tracking-wider transition-colors"
                      >
                        "Did I unplug iron?"
                      </button>
                      <button
                        onClick={() => speakAlexaReassurance("Alexa says: Here is the briefing for AWS Bedrock AgentCore Runtime.")}
                        className="px-3 py-1 rounded-full bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 font-mono text-[9px] tracking-wider transition-colors"
                      >
                        "What is AgentCore?"
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-center py-16 text-zinc-500 font-mono text-sm">
                  No preview card data available for this template.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
