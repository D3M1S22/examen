import React, { useState, useEffect } from "react";
import useSWR from "swr";
import { EchoShowCardResponse } from "@/types/schemas";
import { speakAlexaReassurance } from "@/utils/audioEffects";

interface EchoShowModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialTemplate?: string;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";
const fetcher = (url: string) => fetch(`${API_URL}${url}`).then((res) => res.json());

export function EchoShowModal({
  isOpen,
  onClose,
  initialTemplate = "DEEP_BRIEFING_VIEWER",
}: EchoShowModalProps) {
  const [template, setTemplate] = useState(initialTemplate);
  const [echoTime, setEchoTime] = useState("");

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

  if (!isOpen) return null;

  const handleSpeakCard = () => {
    if (cardData?.voice_summary) {
      speakAlexaReassurance(cardData.voice_summary);
    }
  };

  const templates = [
    { id: "DEEP_BRIEFING_VIEWER", label: "📚 Deep Briefing" },
    { id: "SOCIAL_PROFILE_CARD", label: "👤 Social Profile" },
    { id: "SOCIAL_COMMITMENTS_CARD", label: "🤝 Commitments" },
    { id: "ACTION_VERIFIED_BADGE", label: "🛡️ Peace of Mind" },
    { id: "DAILY_ACTIONS_RECAP", label: "📋 Daily Recap" },
    { id: "SESSION_DOSSIER_VIEWER", label: "🏛️ Session Dossier" },
  ];

  return (
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
            className="text-zinc-400 hover:text-white font-mono text-[11px] tracking-wider uppercase px-2 py-1 rounded bg-zinc-800/80"
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
          <div className="bg-[#08090b] border border-white/5 rounded-2xl overflow-hidden min-h-[520px] flex flex-col relative text-zinc-100">
            {/* Echo System Bar */}
            <div className="bg-black/60 px-6 py-3 flex items-center justify-between border-b border-white/5">
              <div className="font-mono text-base font-bold text-white tracking-wider">
                {echoTime || "12:00"}
              </div>

              <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-950/60 border border-cyan-500/40 text-cyan-300 font-mono text-[10px] tracking-widest uppercase">
                <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
                <span>Alexa+ Ambient Ext-App</span>
              </div>

              <div className="flex items-center gap-3 text-secondary text-xs font-mono">
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
                    Rendering Echo Show Card...
                  </div>
                </div>
              ) : cardData ? (
                <div className="space-y-6 flex-1 flex flex-col justify-between">
                  {/* Card Header */}
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <span className="px-2.5 py-0.5 rounded bg-cyan-950/70 text-cyan-300 border border-cyan-500/30 font-mono text-[9px] tracking-widest uppercase font-bold">
                          {cardData.header_badge || cardData.card_type}
                        </span>
                        <span className="font-mono text-[9px] text-zinc-500 tracking-widest uppercase">
                          {cardData.timestamp ? cardData.timestamp.replace("T", " ").substring(0, 19) : ""}
                        </span>
                      </div>
                      <button
                        onClick={handleSpeakCard}
                        className="px-3 py-1 rounded-full bg-white/5 hover:bg-white/10 border border-white/10 text-cyan-300 font-mono text-[9px] tracking-widest uppercase flex items-center gap-1.5 transition-colors"
                      >
                        <span>🔊</span>
                        <span>Read Aloud</span>
                      </button>
                    </div>

                    <h1 className="font-serif text-[32px] sm:text-[38px] text-white leading-tight mb-4">
                      {cardData.title}
                    </h1>

                    {/* Card Body Data */}
                    <div className="bg-[#12141a] border border-white/5 rounded-xl p-5 space-y-4">
                      {cardData.display_data?.explanatory_synthesis && (
                        <div className="text-amber-200/90 font-sans text-body-md leading-relaxed">
                          ⚡ {cardData.display_data.explanatory_synthesis}
                        </div>
                      )}

                      {cardData.display_data?.summary && (
                        <div className="text-zinc-300 font-sans text-body-md leading-relaxed">
                          {cardData.display_data.summary}
                        </div>
                      )}

                      {cardData.display_data?.facts && (
                        <ul className="space-y-2">
                          {cardData.display_data.facts.map((f: string, i: number) => (
                            <li key={i} className="flex items-start gap-2 text-zinc-300 text-body-sm font-sans">
                              <span className="text-cyan-400 font-bold">•</span>
                              <span>{f}</span>
                            </li>
                          ))}
                        </ul>
                      )}

                      {cardData.display_data?.items && (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          {cardData.display_data.items.map((item: any, i: number) => (
                            <div key={i} className="p-3 rounded-lg bg-black/40 border border-white/5 flex items-center justify-between">
                              <span className="font-sans text-body-sm text-zinc-200">{item.title || item.action_type || item.description}</span>
                              <span className="font-mono text-[9px] text-emerald-400 uppercase font-bold">{item.status || "VERIFIED"}</span>
                            </div>
                          ))}
                        </div>
                      )}

                      {cardData.display_data?.commitments && (
                        <div className="space-y-2">
                          <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase">Mutual Commitments:</div>
                          {cardData.display_data.commitments.map((cmt: any, i: number) => (
                            <div key={i} className="p-2.5 rounded bg-black/40 text-sm font-sans text-zinc-200 flex items-center gap-2">
                              <span>🤝</span>
                              <span>{typeof cmt === "object" ? cmt.description : String(cmt)}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Alexa Voice Speech Synthesis Box */}
                  <div className="mt-6 pt-4 border-t border-white/5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-full bg-cyan-500/20 border border-cyan-400/40 flex items-center justify-center text-cyan-300 shrink-0">
                        💬
                      </div>
                      <div>
                        <div className="font-mono text-[8px] text-zinc-400 tracking-widest uppercase">
                          Alexa Voice Output
                        </div>
                        <div className="font-sans text-xs text-zinc-200 italic">
                          "{cardData.voice_summary || "Here is your updated briefing from EXAMEN."}"
                        </div>
                      </div>
                    </div>

                    {cardData.suggested_prompts && cardData.suggested_prompts.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        {cardData.suggested_prompts.map((p, idx) => (
                          <button
                            key={idx}
                            onClick={() => speakAlexaReassurance(`You asked: ${p}. Corroboration is registered nominal.`)}
                            className="px-3 py-1 rounded-full bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 font-mono text-[9px] tracking-wider transition-colors"
                          >
                            "{p}"
                          </button>
                        ))}
                      </div>
                    )}
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
    </div>
  );
}
