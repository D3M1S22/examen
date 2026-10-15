"use client";

import React, { useEffect, useState, useMemo } from "react";
import { createPortal } from "react-dom";
import { BriefingReport } from "@/types/schemas";
import { speakAlexaReassurance } from "@/utils/audioEffects";
import { MarkdownRenderer } from "./MarkdownRenderer";
import {
  generateTopicMarkdown,
  downloadTextFile,
  sanitizeFilename,
} from "@/utils/dossierExport";

interface TopicDetailModalProps {
  topic: BriefingReport | null;
  isOpen: boolean;
  onClose: () => void;
}

export function TopicDetailModal({ topic, isOpen, onClose }: TopicDetailModalProps) {
  const [mounted, setMounted] = useState(false);
  const [copied, setCopied] = useState(false);
  const [broadcasting, setBroadcasting] = useState(false);
  const [viewMode, setViewMode] = useState<"visualizer" | "raw" | "cards">("visualizer");

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

  const fullMarkdown = useMemo(() => {
    if (!topic) return "";
    return generateTopicMarkdown(topic);
  }, [topic]);

  if (!isOpen || !mounted || !topic) return null;

  const topicSlug = sanitizeFilename(topic.topic_title || "topic_briefing", ".md");

  const handleCopy = () => {
    if (!fullMarkdown) return;
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(fullMarkdown).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }).catch(() => {});
    }
  };

  const handleDownload = () => {
    if (!fullMarkdown) return;
    downloadTextFile(fullMarkdown, topicSlug);
  };

  const handleBroadcast = () => {
    setBroadcasting(true);
    const summaryFirst = Array.isArray(topic.executive_summary) ? topic.executive_summary[0] : "";
    const speech = `Topic briefing for ${topic.topic_title || "this topic"}: ${
      topic.explanatory_synthesis ||
      summaryFirst ||
      "Synthesized analysis completed."
    }`;
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
        className="relative w-full max-w-4xl my-auto bg-[#14161a] border border-[#2b303c] rounded-2xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150 text-zinc-100"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="bg-[#181a20] p-6 sm:p-8 border-b border-white/5 relative">
          <button
            onClick={onClose}
            className="absolute top-6 right-6 w-9 h-9 rounded-lg bg-white/5 hover:bg-white/10 text-zinc-400 hover:text-white flex items-center justify-center transition-colors text-lg cursor-pointer"
            aria-label="Close"
          >
            ✕
          </button>

          <div className="font-mono text-[9px] text-amber-400 tracking-[0.2em] uppercase mb-2 flex items-center gap-2 font-bold">
            <span>📚</span>
            <span>
              AUTONOMOUS TOPIC RESEARCH DOSSIER //{" "}
              {topic.context_type?.replace(/_/g, " ").toUpperCase() || "GENERAL"}
            </span>
          </div>

          <h2 className="font-serif text-[28px] sm:text-[34px] text-white leading-tight mb-2 pr-12 font-bold">
            {topic.topic_title}
          </h2>

          <div className="flex flex-wrap items-center justify-between gap-4 pt-1">
            <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase flex items-center gap-2">
              <span>
                SYNTHESIZED{" "}
                {topic.created_at
                  ? topic.created_at.replace("T", " ").substring(0, 19)
                  : "RECENT"}{" "}
                UTC
              </span>
              <span>•</span>
              <span className="text-cyan-400 font-semibold">AWS BEDROCK AGENTCORE</span>
            </div>

            {/* View Mode Switcher & Quick Actions in Header */}
            <div className="flex items-center gap-2 flex-wrap">
              <div className="flex items-center bg-black/60 p-0.5 rounded-lg border border-white/10 font-mono text-[10px]">
                <button
                  onClick={() => setViewMode("visualizer")}
                  className={`px-3 py-1 rounded-md transition-colors flex items-center gap-1.5 cursor-pointer ${
                    viewMode === "visualizer"
                      ? "bg-amber-400 text-black font-bold shadow-sm"
                      : "text-zinc-400 hover:text-white"
                  }`}
                  title="Formatted Markdown visualizer with citations and deep-dive specs"
                >
                  <span>📖</span>
                  <span>Visualizer</span>
                </button>
                <button
                  onClick={() => setViewMode("raw")}
                  className={`px-3 py-1 rounded-md transition-colors flex items-center gap-1.5 cursor-pointer ${
                    viewMode === "raw"
                      ? "bg-amber-400 text-black font-bold shadow-sm"
                      : "text-zinc-400 hover:text-white"
                  }`}
                  title="View raw Markdown syntax"
                >
                  <span>💻</span>
                  <span>Raw Markdown</span>
                </button>
                <button
                  onClick={() => setViewMode("cards")}
                  className={`px-3 py-1 rounded-md transition-colors flex items-center gap-1.5 cursor-pointer ${
                    viewMode === "cards"
                      ? "bg-amber-400 text-black font-bold shadow-sm"
                      : "text-zinc-400 hover:text-white"
                  }`}
                  title="View separate analytical cards"
                >
                  <span>📑</span>
                  <span>Cards</span>
                </button>
              </div>

              <button
                onClick={handleDownload}
                className="px-3 py-1.5 rounded-lg bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-500/40 text-cyan-300 font-mono text-[10px] tracking-wider uppercase font-bold flex items-center gap-1.5 transition-colors cursor-pointer shadow-sm"
                title={`Download ${topicSlug}`}
              >
                <span>💾</span>
                <span>Download .md</span>
              </button>
            </div>
          </div>
        </div>

        {/* Body */}
        <div className="p-6 sm:p-8 space-y-6 max-h-[70vh] overflow-y-auto">
          {viewMode === "visualizer" ? (
            /* MARKDOWN VISUALIZER VIEW: Full synthesized document rendered via MarkdownRenderer */
            <div className="space-y-3">
              <MarkdownRenderer
                content={fullMarkdown}
                allowRawToggle={true}
                defaultMode="rendered"
                title={topic.topic_title}
                filename={topicSlug}
                accentColor="amber"
                showDownloadButton={true}
                showCopyButton={true}
              />
            </div>
          ) : viewMode === "raw" ? (
            /* RAW MARKDOWN VIEW: Monospaced syntax view */
            <div className="space-y-3">
              <div className="flex items-center justify-between font-mono text-[10px] text-zinc-400 uppercase tracking-wider">
                <span>Complete Synthesized Markdown Syntax</span>
                <span>{fullMarkdown.split(/\s+/).filter(Boolean).length} words</span>
              </div>
              <pre className="font-mono text-xs text-zinc-300 bg-[#0a0c10] border border-white/10 rounded-xl p-5 overflow-x-auto whitespace-pre-wrap leading-relaxed select-text shadow-inner">
                {fullMarkdown}
              </pre>
            </div>
          ) : (
            /* STRUCTURED CARDS VIEW */
            <>
              {/* Explanatory Synthesis Box */}
              {topic.explanatory_synthesis && (
                <div className="bg-gradient-to-r from-amber-950/40 to-black/40 border border-amber-500/40 rounded-xl p-5 shadow-inner space-y-2">
                  <div className="font-mono text-[9px] text-amber-300 tracking-[0.2em] uppercase font-bold flex items-center gap-2">
                    <span>⚡</span>
                    <span>EXPLANATORY SYNTHESIS & CORE THESIS</span>
                  </div>
                  <p className="font-sans text-sm sm:text-base text-amber-100/90 leading-relaxed">
                    {topic.explanatory_synthesis}
                  </p>
                </div>
              )}

              {/* Executive Summary */}
              {Array.isArray(topic.executive_summary) && topic.executive_summary.length > 0 && (
                <div>
                  <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase mb-3 font-bold">
                    Key Insights & Cognitive Summary
                  </div>
                  <div className="bg-[#0e1014] border border-[#232731] rounded-xl p-5 space-y-3 font-sans text-xs sm:text-sm text-zinc-200 leading-relaxed">
                    {topic.executive_summary.map((point, idx) => (
                      <div key={idx} className="flex items-start gap-3">
                        <span className="text-amber-400 select-none font-bold">▪</span>
                        <span>{point}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Action Items */}
              {Array.isArray(topic.action_items) && topic.action_items.length > 0 && (
                <div>
                  <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase mb-3 font-bold">
                    Action Items & Follow-Up Inquiries
                  </div>
                  <div className="bg-[#0e1014] border border-[#232731] rounded-xl p-5 space-y-2">
                    {topic.action_items.map((act, idx) => (
                      <div key={idx} className="flex items-start gap-3 font-sans text-xs sm:text-sm text-zinc-200">
                        <span className="text-emerald-400 select-none font-bold">✓</span>
                        <span>{act}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Web Sources & Citations */}
              {Array.isArray(topic.web_sources) && topic.web_sources.length > 0 && (
                <div>
                  <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase mb-3 font-bold">
                    Corroborating Web Citations ({topic.web_sources.length})
                  </div>
                  <div className="space-y-2">
                    {topic.web_sources.map((src, idx) => {
                      const url = typeof src === "string" ? src : (src as any)?.url || "";
                      const label = typeof src === "string" ? src : (src as any)?.title || url || "Source";
                      return (
                        <a
                          key={idx}
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="block bg-[#0e1014] hover:bg-[#161a22] border border-[#232731] rounded-lg p-3 font-mono text-[11px] text-amber-200/90 hover:text-amber-300 truncate transition-colors"
                        >
                          🔗 {label}
                        </a>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Deep Dive Markdown Visualizer */}
              {topic.deep_dive_markdown && (
                <div className="space-y-2">
                  <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase font-bold flex items-center justify-between">
                    <span>Deep Dive Technical Specification & Markdown</span>
                    <span className="text-cyan-400">Interactive Visualizer</span>
                  </div>
                  <MarkdownRenderer
                    content={topic.deep_dive_markdown}
                    allowRawToggle={true}
                    defaultMode="rendered"
                    title={topic.topic_title}
                    filename={topicSlug}
                    accentColor="cyan"
                    showDownloadButton={true}
                    showCopyButton={true}
                  />
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="bg-[#0e1014] p-4 sm:p-6 border-t border-white/5 flex flex-wrap items-center justify-between gap-3">
          <div className="text-zinc-400 font-mono text-[9px] tracking-widest uppercase">
            {copied && <span className="text-emerald-400 font-bold">✅ Copied full markdown to clipboard!</span>}
            {broadcasting && <span className="text-amber-400 font-bold">🔊 Broadcasting to Alexa Echo...</span>}
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleBroadcast}
              className="px-4 py-2.5 rounded-lg border border-[#2b303c] hover:border-amber-400 bg-transparent text-zinc-300 hover:text-white font-mono text-[10px] tracking-widest uppercase font-bold flex items-center gap-2 transition-colors cursor-pointer"
            >
              <span>🔊</span>
              <span>Alexa Voice Readout</span>
            </button>

            <button
              onClick={handleDownload}
              className="px-4 py-2.5 rounded-lg border border-cyan-500/40 bg-cyan-950/60 hover:bg-cyan-900 text-cyan-300 font-mono text-[10px] tracking-widest uppercase font-bold flex items-center gap-2 transition-colors cursor-pointer"
            >
              <span>💾</span>
              <span>Download .md</span>
            </button>

            <button
              onClick={handleCopy}
              className="px-4 py-2.5 rounded-lg border border-[#2b303c] bg-zinc-800 hover:bg-zinc-700 text-white font-mono text-[10px] tracking-widest uppercase font-bold flex items-center gap-2 transition-colors cursor-pointer"
            >
              <span>📋</span>
              <span>Copy Markdown</span>
            </button>

            <button
              onClick={onClose}
              className="px-5 py-2.5 rounded-lg bg-amber-400 hover:bg-amber-300 text-black font-mono text-[10px] tracking-widest uppercase font-bold transition-colors cursor-pointer"
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
