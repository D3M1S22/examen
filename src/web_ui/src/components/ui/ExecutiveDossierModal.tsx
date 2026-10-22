"use client";

import React, { useState, useEffect, useMemo } from "react";
import { createPortal } from "react-dom";
import { SocialEntity } from "@/types/schemas";
import { StatusBadge } from "./StatusBadge";
import {
  generateContactMarkdown,
  downloadTextFile,
  sanitizeFilename,
} from "@/utils/dossierExport";

interface ExecutiveDossierModalProps {
  contact: SocialEntity | null;
  isOpen: boolean;
  onClose: () => void;
  onEnrich?: (contactId: string) => Promise<void>;
  onToggleCommitment?: (commitmentId: string, action: "fulfill" | "cancel") => Promise<void>;
  /** Manual curation (docs/next_steps/manual_curation/04 §4) */
  onEdit?: (contact: SocialEntity) => void;
  onDelete?: (contact: SocialEntity) => void;
  /** A web search re-run after an edit is in progress for this contact */
  reSearching?: boolean;
  /** Why the last re-run found nothing (insufficient_anchors | error) */
  enrichFailure?: string | null;
}

export function ExecutiveDossierModal({
  contact,
  isOpen,
  onClose,
  onEnrich,
  onToggleCommitment,
  onEdit,
  onDelete,
  reSearching = false,
  enrichFailure = null,
}: ExecutiveDossierModalProps) {
  const [mounted, setMounted] = useState(false);
  const [isEnriching, setIsEnriching] = useState(false);
  const [enrichSuccess, setEnrichSuccess] = useState(false);
  const [viewMode, setViewMode] = useState<"visualizer" | "raw">("visualizer");
  const [copied, setCopied] = useState(false);

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
    if (!contact) return "";
    return generateContactMarkdown(contact);
  }, [contact]);

  if (!isOpen || !mounted || !contact) return null;

  const webProfile = contact.web_profile;
  const disambiguation = webProfile?.disambiguation_report;
  const rawCommitments = Array.isArray(contact.commitments) ? contact.commitments : [];

  const linkedInUrl = webProfile?.linkedin_url || disambiguation?.canonical_linkedin_url;
  const githubUrl = webProfile?.github_url || disambiguation?.canonical_github_url;
  const websiteUrl = contact.website_url || webProfile?.website_url;

  const contactName = contact.name || contact.person_name || "Contact";
  const contactSlug = sanitizeFilename(contactName, ".md");
  const matchConfidence = disambiguation?.confidence_score ?? webProfile?.confidence_score;
  const expertise = Array.isArray(webProfile?.areas_of_expertise) ? webProfile.areas_of_expertise : [];

  const handleRunEnrich = async () => {
    if (!onEnrich || isEnriching) return;
    setIsEnriching(true);
    setEnrichSuccess(false);
    try {
      await onEnrich(contact.id);
      setEnrichSuccess(true);
      setTimeout(() => setEnrichSuccess(false), 3000);
    } catch (err) {
      console.error(err);
    } finally {
      setIsEnriching(false);
    }
  };

  const handleCopyMarkdown = () => {
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
    downloadTextFile(fullMarkdown, contactSlug);
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[9999] overflow-y-auto bg-black/85 backdrop-blur-md flex items-center justify-center p-4 sm:p-6"
      onClick={onClose}
      aria-modal="true"
      role="dialog"
    >
      <div
        className="relative w-full max-w-3xl my-auto bg-[#14161a] border border-[#2b303c] rounded-2xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150 text-zinc-100"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top Header Card Banner */}
        <div className="bg-gradient-to-r from-[#191c24] to-[#121419] p-6 sm:p-8 border-b border-white/5 relative">
          <button
            onClick={onClose}
            className="absolute top-6 right-6 w-9 h-9 rounded-lg bg-white/5 hover:bg-white/10 text-zinc-400 hover:text-white flex items-center justify-center transition-colors text-lg cursor-pointer"
            aria-label="Close"
          >
            ✕
          </button>

          <div className="flex flex-col sm:flex-row items-start justify-between gap-5 pr-8">
            <div className="flex items-start gap-4">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-amber-500/20 to-amber-700/30 border border-amber-500/40 flex items-center justify-center text-white font-serif text-2xl font-bold shrink-0 shadow-lg">
                {contactName.substring(0, 2).toUpperCase()}
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-3 mb-1">
                  <h2 className="font-serif text-[26px] sm:text-[30px] text-white leading-tight font-bold">
                    {contactName}
                  </h2>
                  {matchConfidence != null && (
                    <StatusBadge
                      status="verified"
                      label={`⚡ ${(matchConfidence * 100).toFixed(0)}% MATCH`}
                    />
                  )}
                </div>
                <div className="font-sans text-sm sm:text-base text-amber-200/80 mb-2">
                  {contact.company_or_role || "Professional Contact"}
                </div>
                <div className="flex flex-wrap items-center gap-4 font-mono text-[9px] text-zinc-400 tracking-widest uppercase">
                  {contact.contact_info && (
                    <span className="flex items-center gap-1.5">
                      <span>✉️</span> {contact.contact_info}
                    </span>
                  )}
                  {contact.location_encountered && (
                    <span className="flex items-center gap-1.5">
                      <span>📍</span> {contact.location_encountered}
                    </span>
                  )}
                  <span className="flex items-center gap-1.5">
                    <span>📅</span> {contact.timestamp ? contact.timestamp.split("T")[0] : "Recent"}
                  </span>
                </div>
              </div>
            </div>

            {/* Header Controls: Raw Toggler & Download */}
            <div className="flex items-center gap-2 self-end sm:self-start">
              <div className="flex items-center bg-black/60 p-0.5 rounded-lg border border-white/10 font-mono text-[10px]">
                <button
                  onClick={() => setViewMode("visualizer")}
                  className={`px-2.5 py-1 rounded-md transition-colors flex items-center gap-1 cursor-pointer ${
                    viewMode === "visualizer"
                      ? "bg-amber-400 text-black font-bold shadow-sm"
                      : "text-zinc-400 hover:text-white"
                  }`}
                >
                  <span>📖</span>
                  <span>Visualizer</span>
                </button>
                <button
                  onClick={() => setViewMode("raw")}
                  className={`px-2.5 py-1 rounded-md transition-colors flex items-center gap-1 cursor-pointer ${
                    viewMode === "raw"
                      ? "bg-amber-400 text-black font-bold shadow-sm"
                      : "text-zinc-400 hover:text-white"
                  }`}
                >
                  <span>💻</span>
                  <span>Raw</span>
                </button>
              </div>

              <button
                onClick={handleDownload}
                className="px-3 py-1.5 rounded-lg bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-500/40 text-cyan-300 font-mono text-[10px] tracking-wider uppercase font-bold flex items-center gap-1.5 transition-colors cursor-pointer shadow-sm"
                title={`Download ${contactSlug}`}
              >
                <span>💾</span>
                <span>Download .md</span>
              </button>
            </div>
          </div>
        </div>

        {/* Modal Body */}
        <div className="p-6 sm:p-8 space-y-6 max-h-[70vh] overflow-y-auto">
          {viewMode === "raw" ? (
            /* RAW SYNTAX VIEW */
            <div className="space-y-3">
              <div className="flex items-center justify-between font-mono text-[10px] text-zinc-400 uppercase tracking-wider">
                <span>Executive Dossier Markdown Syntax</span>
                <span>{fullMarkdown.split(/\s+/).filter(Boolean).length} words</span>
              </div>
              <pre className="font-mono text-xs text-zinc-300 bg-[#0a0c10] border border-white/10 rounded-xl p-5 overflow-x-auto whitespace-pre-wrap leading-relaxed select-text shadow-inner">
                {fullMarkdown}
              </pre>
            </div>
          ) : (
            /* STRUCTURED VISUALIZER VIEW */
            <>
              {/* Verified External Profiles Bar */}
              {(linkedInUrl || githubUrl || websiteUrl) && (
                <div className="flex flex-wrap items-center gap-3 p-3.5 bg-[#0e1014] border border-[#232731] rounded-xl">
                  <span className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase">
                    Verified Profiles:
                  </span>
                  {linkedInUrl && (
                    <a
                      href={linkedInUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[#0077b5]/15 border border-[#0077b5]/40 text-[#70b5f9] font-mono text-[10px] tracking-wider uppercase hover:bg-[#0077b5]/30 transition-colors"
                    >
                      <span>💼</span>
                      <span>LinkedIn</span>
                    </a>
                  )}
                  {githubUrl && (
                    <a
                      href={githubUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[#24292e]/60 border border-white/20 text-[#e6edf3] font-mono text-[10px] tracking-wider uppercase hover:bg-white/10 transition-colors"
                    >
                      <span>🐙</span>
                      <span>GitHub</span>
                    </a>
                  )}
                  {websiteUrl && (
                    <a
                      href={websiteUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 font-mono text-[10px] tracking-wider uppercase hover:bg-emerald-500/30 transition-colors"
                    >
                      <span>🌐</span>
                      <span>Website</span>
                      {contact.website_url && !webProfile?.website_url && (
                        <span className="text-[7px] bg-emerald-400/20 px-1 rounded text-emerald-200">
                          VOICE
                        </span>
                      )}
                    </a>
                  )}
                </div>
              )}

              {/* Executive Bio / Web Profile */}
              <div>
                <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase mb-2 flex items-center justify-between">
                  <span>Executive Intelligence Dossier</span>
                  {webProfile?.enriched_at && (
                    <span className="text-amber-400 font-semibold">
                      Enriched {webProfile.enriched_at.split("T")[0]}
                    </span>
                  )}
                </div>
                <div className="bg-[#0e1014] border border-[#232731] rounded-xl p-4 font-sans text-sm text-zinc-200 leading-relaxed space-y-2">
                  {webProfile?.headline && (
                    <div className="font-sans text-base text-white font-semibold">
                      {webProfile.headline}
                    </div>
                  )}
                  {webProfile?.bio_summary ? (
                    <p>{webProfile.bio_summary}</p>
                  ) : (
                    <span className="italic opacity-60">
                      Passively extracted encounter metadata. Click "Run Live AI Enrichment" below to synthesize LinkedIn, GitHub, and professional background.
                    </span>
                  )}
                </div>
              </div>

              {/* Areas of Expertise */}
              {expertise.length > 0 && (
                <div>
                  <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase mb-2">
                    Areas of Expertise
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {expertise.map((area, idx) => (
                      <span
                        key={idx}
                        className="px-3 py-1 rounded-md bg-cyan-500/10 border border-cyan-500/30 font-mono text-[10px] text-cyan-200/90"
                      >
                        {area}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Disambiguation & Source Integrity Audit Drawer */}
              {disambiguation && (
                <div className="bg-[#101217] border border-amber-500/30 rounded-xl p-5 space-y-4">
                  <div className="flex items-center justify-between border-b border-white/5 pb-3">
                    <div className="flex items-center gap-2">
                      <span className="text-amber-400 text-base">🛡️</span>
                      <span className="font-mono text-[10px] text-amber-300 tracking-widest uppercase font-bold">
                        Source Disambiguation & Anti-Contamination Audit
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[9px] text-zinc-400">CERTAINTY:</span>
                      <span className="font-mono text-xs font-bold text-amber-400">
                        {(disambiguation.confidence_score * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>

                  {/* Deduplication Rationale */}
                  {disambiguation.rationale && (
                    <div>
                      <div className="font-mono text-[8px] text-zinc-400 tracking-widest uppercase mb-1">
                        Deduplication Rationale
                      </div>
                      <p className="font-sans text-xs text-zinc-300 italic leading-relaxed">
                        "{disambiguation.rationale}"
                      </p>
                    </div>
                  )}

                  {/* Corroborated Facts */}
                  {Array.isArray(disambiguation.clean_combined_facts) &&
                    disambiguation.clean_combined_facts.length > 0 && (
                      <div>
                        <div className="font-mono text-[8px] text-zinc-400 tracking-widest uppercase mb-1.5">
                          Corroborated Facts
                        </div>
                        <ul className="space-y-1">
                          {disambiguation.clean_combined_facts.map((fact, i) => (
                            <li key={i} className="font-sans text-xs text-emerald-300 flex items-start gap-2">
                              <span className="text-emerald-400 mt-0.5">✓</span>
                              <span>{fact}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                  {/* Source Diagnostics Pill Row */}
                  <div className="flex items-center gap-4 pt-2 font-mono text-[8px]">
                    <div className="flex items-center gap-1.5 text-emerald-400">
                      <span>Verified Sources:</span>
                      <span className="px-1.5 py-0.5 rounded bg-emerald-950 border border-emerald-500/40 font-bold">
                        {disambiguation.verified_source_indices?.length || 0}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5 text-rose-400">
                      <span>Rejected Noise/Homonyms:</span>
                      <span className="px-1.5 py-0.5 rounded bg-rose-950 border border-rose-500/40 font-bold">
                        {disambiguation.rejected_source_indices?.length || 0}
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* Bilateral Commitments Section */}
              <div>
                <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase mb-2 flex items-center justify-between">
                  <span>Bilateral Commitments & Action Items</span>
                  <span className="text-white font-bold">{rawCommitments.length} Logged</span>
                </div>

                {rawCommitments.length > 0 ? (
                  <div className="space-y-3">
                    {rawCommitments.map((c: any, idx: number) => {
                      const isObj = typeof c === "object" && c !== null;
                      const desc = isObj ? c.description : String(c);
                      const debtor = isObj ? c.debtor : "user";
                      const status = isObj ? c.status : "open";
                      const commId = isObj ? c.id : null;

                      return (
                        <div
                          key={idx}
                          className="bg-[#0e1014] border border-[#232731] rounded-xl p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3"
                        >
                          <div className="flex items-start gap-3">
                            <span className="text-lg mt-0.5">
                              {debtor === "user" ? "📤" : "📥"}
                            </span>
                            <div>
                              <div className="font-mono text-[8px] text-zinc-400 tracking-widest uppercase mb-1">
                                {debtor === "user" ? "YOU PROMISED" : `${contactName.toUpperCase()} PROMISED`}
                              </div>
                              <p className="font-sans text-xs sm:text-sm text-white leading-snug">
                                "{desc}"
                              </p>
                            </div>
                          </div>

                          <div className="flex items-center gap-2 self-end sm:self-center shrink-0">
                            <StatusBadge status={status} size="sm" />
                            {commId && onToggleCommitment && status === "open" && (
                              <button
                                onClick={() => onToggleCommitment(commId, "fulfill")}
                                className="px-3 py-1 rounded bg-emerald-950/70 border border-emerald-500/50 text-emerald-300 font-mono text-[9px] tracking-wider hover:bg-emerald-900 transition-colors uppercase cursor-pointer"
                              >
                                Fulfill
                              </button>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="bg-[#0e1014] border border-dashed border-[#232731] rounded-xl p-4 text-center text-zinc-500 text-xs sm:text-sm font-sans italic opacity-60">
                    No active commitments logged with this contact.
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer Actions */}
        <div className="bg-[#0e1014] p-4 sm:p-6 border-t border-white/5 flex flex-wrap items-center justify-between gap-3">
          <div className="text-zinc-400 font-mono text-[9px] tracking-widest uppercase">
            {reSearching && (
              <span className="text-amber-300 font-bold flex items-center gap-2">
                <span className="w-3 h-3 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
                Re-searching the web with the new details…
              </span>
            )}
            {!reSearching && enrichFailure && (
              <span className="text-rose-300 font-bold normal-case tracking-normal font-sans text-[11px]">
                {enrichFailure === "insufficient_anchors"
                  ? "Web search skipped: add the company or role to tell this person apart."
                  : "The web search failed; you can run it again."}
              </span>
            )}
            {enrichSuccess && (
              <span className="text-emerald-400 font-bold">✅ Enrichment updated successfully!</span>
            )}
            {copied && (
              <span className="text-emerald-400 font-bold">✅ Copied contact markdown!</span>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {onEdit && (
              <button
                onClick={() => onEdit(contact)}
                className="px-4 py-2.5 rounded-lg border border-[#2b303c] bg-zinc-800 hover:bg-zinc-700 text-white font-mono text-[10px] tracking-widest uppercase font-bold flex items-center gap-2 transition-colors cursor-pointer"
              >
                <span>✏️</span>
                <span>Edit</span>
              </button>
            )}
            {onDelete && (
              <button
                onClick={() => onDelete(contact)}
                className="px-4 py-2.5 rounded-lg border border-rose-500/40 bg-rose-950/40 hover:bg-rose-900/60 text-rose-300 font-mono text-[10px] tracking-widest uppercase font-bold flex items-center gap-2 transition-colors cursor-pointer"
              >
                <span>🗑️</span>
                <span>Delete</span>
              </button>
            )}
            <button
              onClick={handleDownload}
              className="px-4 py-2.5 rounded-lg border border-cyan-500/40 bg-cyan-950/60 hover:bg-cyan-900 text-cyan-300 font-mono text-[10px] tracking-widest uppercase font-bold flex items-center gap-2 transition-colors cursor-pointer"
            >
              <span>💾</span>
              <span>Download .md</span>
            </button>

            <button
              onClick={handleCopyMarkdown}
              className="px-4 py-2.5 rounded-lg border border-[#2b303c] bg-zinc-800 hover:bg-zinc-700 text-white font-mono text-[10px] tracking-widest uppercase font-bold flex items-center gap-2 transition-colors cursor-pointer"
            >
              <span>📋</span>
              <span>Copy Markdown</span>
            </button>

            {onEnrich && (
              <button
                onClick={handleRunEnrich}
                disabled={isEnriching || reSearching}
                className="px-5 py-2.5 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/40 text-amber-300 font-mono text-[10px] tracking-widest uppercase font-bold flex items-center gap-2 transition-all cursor-pointer disabled:opacity-50"
              >
                {isEnriching ? (
                  <>
                    <span className="w-3 h-3 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
                    <span>AI Searching Web...</span>
                  </>
                ) : (
                  <>
                    <span>⚡</span>
                    <span>Run Live AI Enrichment</span>
                  </>
                )}
              </button>
            )}

            <button
              onClick={onClose}
              className="px-5 py-2.5 rounded-lg bg-white/10 hover:bg-white/20 text-white font-mono text-[10px] tracking-widest uppercase font-bold transition-colors cursor-pointer"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
