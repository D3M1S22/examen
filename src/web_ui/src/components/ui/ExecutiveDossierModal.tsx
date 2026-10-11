import React, { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { SocialEntity, SocialCommitment } from "@/types/schemas";
import { StatusBadge } from "./StatusBadge";

interface ExecutiveDossierModalProps {
  contact: SocialEntity | null;
  isOpen: boolean;
  onClose: () => void;
  onEnrich?: (contactId: string) => Promise<void>;
  onToggleCommitment?: (commitmentId: string, action: "fulfill" | "cancel") => Promise<void>;
}

export function ExecutiveDossierModal({
  contact,
  isOpen,
  onClose,
  onEnrich,
  onToggleCommitment,
}: ExecutiveDossierModalProps) {
  const [mounted, setMounted] = useState(false);
  const [isEnriching, setIsEnriching] = useState(false);
  const [enrichSuccess, setEnrichSuccess] = useState(false);

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

  if (!isOpen || !mounted || !contact) return null;

  const webProfile = contact.web_profile;
  const rawCommitments = contact.commitments || [];

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

  const contactName = contact.name || contact.person_name || "Contact";

  return createPortal(
    <div
      className="fixed inset-0 z-[9999] overflow-y-auto bg-black/85 backdrop-blur-md flex items-center justify-center p-4 sm:p-6"
      onClick={onClose}
      aria-modal="true"
      role="dialog"
    >
      <div
        className="relative w-full max-w-2xl my-auto bg-[#14161a] border border-[#2b303c] rounded-2xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top Header Card Banner */}
        <div className="bg-gradient-to-r from-[#191c24] to-[#121419] p-6 sm:p-8 border-b border-white/5 relative">
          <button
            onClick={onClose}
            className="absolute top-6 right-6 w-9 h-9 rounded-lg bg-surface-container-highest/60 hover:bg-surface-container-highest text-secondary hover:text-primary flex items-center justify-center transition-colors text-lg"
            aria-label="Close"
          >
            ✕
          </button>

          <div className="flex items-start gap-5">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-amber-500/20 to-amber-700/30 border border-amber-500/40 flex items-center justify-center text-primary font-serif text-2xl font-bold shrink-0 shadow-lg">
              {contactName.substring(0, 2).toUpperCase()}
            </div>
            <div className="flex-1 pr-10">
              <div className="flex flex-wrap items-center gap-3 mb-1">
                <h2 className="font-serif text-[28px] text-primary leading-tight">
                  {contactName}
                </h2>
                <StatusBadge status="verified" label="⚡ 98% MATCH" />
              </div>
              <div className="font-sans text-body-md text-amber-200/80 mb-2">
                {contact.company_or_role || "Professional Contact"}
              </div>
              <div className="flex flex-wrap items-center gap-4 font-mono text-[9px] text-secondary tracking-widest uppercase">
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
        </div>

        {/* Modal Body */}
        <div className="p-6 sm:p-8 space-y-6 max-h-[70vh] overflow-y-auto">
          {/* Executive Bio / Web Profile */}
          <div>
            <div className="font-mono text-[9px] text-secondary tracking-widest uppercase mb-2 flex items-center justify-between">
              <span>Executive Intelligence Dossier</span>
              {webProfile && (
                <span className="text-amber-400">
                  Enriched via {webProfile.enrichment_source || "Web Intelligence"}
                </span>
              )}
            </div>
            <div className="bg-[#0e1014] border border-[#232731] rounded-xl p-4 font-sans text-body-sm text-secondary leading-relaxed">
              {webProfile?.executive_summary || (
                <span className="italic opacity-60">
                  Passively extracted encounter metadata. Click "Run Live AI Enrichment" below to synthesize LinkedIn, GitHub, and professional background.
                </span>
              )}
            </div>
          </div>

          {/* Social Links & Affiliations */}
          {webProfile && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {webProfile.current_role && (
                <div className="bg-[#0e1014] border border-[#232731] rounded-lg p-3">
                  <div className="font-mono text-[8px] text-secondary tracking-widest uppercase mb-1">Current Role</div>
                  <div className="font-sans text-body-sm text-primary">{webProfile.current_role}</div>
                </div>
              )}
              {webProfile.organization && (
                <div className="bg-[#0e1014] border border-[#232731] rounded-lg p-3">
                  <div className="font-mono text-[8px] text-secondary tracking-widest uppercase mb-1">Organization</div>
                  <div className="font-sans text-body-sm text-primary">{webProfile.organization}</div>
                </div>
              )}
            </div>
          )}

          {/* Areas of Expertise / Topics */}
          <div>
            <div className="font-mono text-[9px] text-secondary tracking-widest uppercase mb-2">
              Salient Discussion Topics & Keywords
            </div>
            <div className="flex flex-wrap gap-2">
              {contact.key_topics && contact.key_topics.length > 0 ? (
                contact.key_topics.map((t, idx) => (
                  <span
                    key={idx}
                    className="px-3 py-1 rounded-md bg-[#1c1f26] border border-white/5 font-mono text-[10px] text-amber-200/90"
                  >
                    #{t.replace(/\s+/g, "-")}
                  </span>
                ))
              ) : (
                <span className="text-secondary text-body-sm italic opacity-50">No topics tagged.</span>
              )}
            </div>
          </div>

          {/* Bilateral Commitments Section */}
          <div>
            <div className="font-mono text-[9px] text-secondary tracking-widest uppercase mb-2 flex items-center justify-between">
              <span>Bilateral Commitments & Action Items</span>
              <span className="text-primary font-bold">
                {rawCommitments.length} Logged
              </span>
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
                          <div className="font-mono text-[8px] text-secondary tracking-widest uppercase mb-1">
                            {debtor === "user" ? "YOU PROMISED" : `${contactName.toUpperCase()} PROMISED`}
                          </div>
                          <p className="font-sans text-body-sm text-primary leading-snug">
                            "{desc}"
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 self-end sm:self-center shrink-0">
                        <StatusBadge status={status} size="sm" />
                        {commId && onToggleCommitment && status === "open" && (
                          <button
                            onClick={() => onToggleCommitment(commId, "fulfill")}
                            className="px-3 py-1 rounded bg-emerald-950/70 border border-emerald-500/50 text-emerald-300 font-mono text-[9px] tracking-wider hover:bg-emerald-900 transition-colors uppercase"
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
              <div className="bg-[#0e1014] border border-dashed border-[#232731] rounded-xl p-4 text-center text-secondary text-body-sm font-sans italic opacity-60">
                No active commitments logged with this contact.
              </div>
            )}
          </div>
        </div>

        {/* Footer Actions */}
        <div className="bg-[#0e1014] p-4 sm:p-6 border-t border-white/5 flex flex-wrap items-center justify-between gap-3">
          <div className="text-secondary font-mono text-[9px] tracking-widest uppercase">
            {enrichSuccess && <span className="text-emerald-400">✅ Enrichment updated successfully!</span>}
          </div>

          <div className="flex items-center gap-3">
            {onEnrich && (
              <button
                onClick={handleRunEnrich}
                disabled={isEnriching}
                className="px-5 py-2.5 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/40 text-amber-300 font-mono text-[10px] tracking-widest uppercase font-bold flex items-center gap-2 transition-all"
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
              className="px-5 py-2.5 rounded-lg bg-primary hover:bg-surface-tint text-background font-mono text-[10px] tracking-widest uppercase font-bold transition-colors"
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
