import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { BriefingReport } from "@/types/schemas";
import { speakAlexaReassurance } from "@/utils/audioEffects";

interface TopicDetailModalProps {
  topic: BriefingReport | null;
  isOpen: boolean;
  onClose: () => void;
}

export function TopicDetailModal({ topic, isOpen, onClose }: TopicDetailModalProps) {
  const [mounted, setMounted] = useState(false);
  const [copied, setCopied] = useState(false);
  const [broadcasting, setBroadcasting] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === "Escape") onClose();
      };
      window.addEventListener("keydown", handleKeyDown);
      return () => {
        document.body.style.overflow = "unset";
        window.removeEventListener("keydown", handleKeyDown);
      };
    } else {
      document.body.style.overflow = "unset";
    }
  }, [isOpen, onClose]);

  if (!isOpen || !mounted || !topic) return null;

  const handleCopy = () => {
    const text = `# ${topic.topic_title || "Topic Briefing"}\n\n${topic.explanatory_synthesis || ""}\n\n## Executive Summary\n${(topic.executive_summary || []).map(s => `- ${s}`).join("\n")}\n\n## Action Items\n${(topic.action_items || []).map(a => `- ${a}`).join("\n")}`;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleBroadcast = () => {
    setBroadcasting(true);
    const speech = `Topic briefing for ${topic.topic_title || "this topic"}: ${topic.explanatory_synthesis || (topic.executive_summary?.[0] || "Synthesized analysis completed.")}`;
    speakAlexaReassurance(speech);
    setTimeout(() => setBroadcasting(false), 3000);
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[9999] overflow-y-auto bg-black/85 backdrop-blur-md flex items-center justify-center p-4 sm:p-6"
      onClick={onClose}
      aria-modal="true"
      role="dialog"
    >
      <div
        className="relative w-full max-w-3xl my-auto bg-[#14161a] border border-[#2b303c] rounded-2xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="bg-[#181a20] p-6 sm:p-8 border-b border-white/5 relative">
          <button
            onClick={onClose}
            className="absolute top-6 right-6 w-9 h-9 rounded-lg bg-surface-container-highest/60 hover:bg-surface-container-highest text-secondary hover:text-primary flex items-center justify-center transition-colors text-lg"
            aria-label="Close"
          >
            ✕
          </button>

          <div className="font-mono text-[9px] text-amber-400 tracking-[0.2em] uppercase mb-2 flex items-center gap-2">
            <span>📚</span>
            <span>AUTONOMOUS TOPIC RESEARCH DOSSIER // {topic.context_type?.replace(/_/g, " ").toUpperCase()}</span>
          </div>

          <h2 className="font-serif text-[32px] text-primary leading-tight mb-2 pr-10">
            {topic.topic_title}
          </h2>

          <div className="font-mono text-[9px] text-secondary tracking-widest uppercase">
            SYNTHESIZED {topic.created_at ? topic.created_at.replace("T", " ").substring(0, 19) : "RECENT"} UTC • ZERO-SHOT MULTI-TIER REASONER
          </div>
        </div>

        {/* Body */}
        <div className="p-6 sm:p-8 space-y-6 max-h-[70vh] overflow-y-auto">
          {/* Explanatory Synthesis Box (Featured Next_steps feature) */}
          {topic.explanatory_synthesis && (
            <div className="bg-gradient-to-r from-amber-950/40 to-surface-container-low border border-amber-500/40 rounded-xl p-5 shadow-inner">
              <div className="font-mono text-[9px] text-amber-300 tracking-[0.2em] uppercase font-bold mb-2 flex items-center gap-2">
                <span>⚡</span>
                <span>EXPLANATORY SYNTHESIS & CORE THESIS</span>
              </div>
              <p className="font-sans text-body-md text-amber-100/90 leading-relaxed font-normal">
                {topic.explanatory_synthesis}
              </p>
            </div>
          )}

          {/* Executive Summary */}
          <div>
            <div className="font-mono text-[9px] text-secondary tracking-widest uppercase mb-3 font-bold">
              Key Insights & Cognitive Summary
            </div>
            <div className="bg-[#0e1014] border border-[#232731] rounded-xl p-5 space-y-3 font-sans text-body-sm text-secondary leading-relaxed">
              {topic.executive_summary && topic.executive_summary.length > 0 ? (
                topic.executive_summary.map((point, idx) => (
                  <div key={idx} className="flex items-start gap-3 text-primary">
                    <span className="text-amber-400 select-none font-bold">▪</span>
                    <span>{point}</span>
                  </div>
                ))
              ) : (
                <div className="text-secondary opacity-60 italic">No summary points generated.</div>
              )}
            </div>
          </div>

          {/* Action Items */}
          {topic.action_items && topic.action_items.length > 0 && (
            <div>
              <div className="font-mono text-[9px] text-secondary tracking-widest uppercase mb-3 font-bold">
                Action Items & Follow-Up Inquiries
              </div>
              <div className="bg-[#0e1014] border border-[#232731] rounded-xl p-5 space-y-2">
                {topic.action_items.map((act, idx) => (
                  <div key={idx} className="flex items-start gap-3 font-sans text-body-sm text-primary">
                    <span className="text-emerald-400 select-none font-bold">✓</span>
                    <span>{act}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Web Sources & Citations */}
          {topic.web_sources && topic.web_sources.length > 0 && (
            <div>
              <div className="font-mono text-[9px] text-secondary tracking-widest uppercase mb-3 font-bold">
                Corroborating Web Citations ({topic.web_sources.length})
              </div>
              <div className="space-y-2">
                {topic.web_sources.map((src, idx) => (
                  <a
                    key={idx}
                    href={src}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block bg-[#0e1014] hover:bg-[#161a22] border border-[#232731] rounded-lg p-3 font-mono text-[11px] text-amber-200/90 hover:text-amber-300 truncate transition-colors"
                  >
                    🔗 {src}
                  </a>
                ))}
              </div>
            </div>
          )}

          {/* Deep Dive Markdown */}
          {topic.deep_dive_markdown && (
            <div>
              <div className="font-mono text-[9px] text-secondary tracking-widest uppercase mb-3 font-bold">
                Deep Dive Technical Report
              </div>
              <div className="bg-[#0e1014] border border-[#232731] rounded-xl p-5 font-mono text-body-xs text-zinc-300 whitespace-pre-wrap leading-relaxed">
                {topic.deep_dive_markdown}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="bg-[#0e1014] p-4 sm:p-6 border-t border-white/5 flex flex-wrap items-center justify-between gap-3">
          <div className="text-secondary font-mono text-[9px] tracking-widest uppercase">
            {copied && <span className="text-emerald-400 font-bold">✅ Copied to clipboard!</span>}
            {broadcasting && <span className="text-amber-400 font-bold">🔊 Broadcasting to Alexa Echo...</span>}
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleBroadcast}
              className="px-4 py-2.5 rounded-lg border border-[#2b303c] hover:border-amber-400 bg-transparent text-secondary hover:text-primary font-mono text-[10px] tracking-widest uppercase font-bold flex items-center gap-2 transition-colors"
            >
              <span>🔊</span>
              <span>Alexa Voice Readout</span>
            </button>

            <button
              onClick={handleCopy}
              className="px-4 py-2.5 rounded-lg border border-[#2b303c] bg-surface-container-highest hover:bg-surface-container text-primary font-mono text-[10px] tracking-widest uppercase font-bold flex items-center gap-2 transition-colors"
            >
              <span>📋</span>
              <span>Copy Briefing</span>
            </button>

            <button
              onClick={onClose}
              className="px-5 py-2.5 rounded-lg bg-primary hover:bg-surface-tint text-background font-mono text-[10px] tracking-widest uppercase font-bold transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
