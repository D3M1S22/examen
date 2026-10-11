import React, { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { SocialEntity } from "@/types/schemas";

interface FollowUpModalProps {
  contact: SocialEntity | null;
  isOpen: boolean;
  onClose: () => void;
}

export function FollowUpModal({ contact, isOpen, onClose }: FollowUpModalProps) {
  const [mounted, setMounted] = useState(false);
  const [copied, setCopied] = useState(false);
  const [draftText, setDraftText] = useState("");

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

  const contactName = contact ? (contact.name || contact.person_name || "there") : "there";

  useEffect(() => {
    if (contact) {
      const commitmentsStr = (contact.commitments || [])
        .map((c: any) => typeof c === "object" ? c.description : String(c))
        .join("; ");
      const topicsStr = (contact.key_topics || []).slice(0, 3).join(", ");
      const firstName = contactName.split(" ")[0];

      const draft = `Hi ${firstName},\n\nGreat connecting with you earlier! I really enjoyed our discussion around ${topicsStr || "our recent collaboration"}.\n\nAs promised, I wanted to follow up regarding: ${commitmentsStr || "our next steps and scheduling time to sync"}.\n\nLet me know if you have some availability this week.\n\nBest regards,\n[Your Name]`;
      setDraftText(draft);
    }
  }, [contact, contactName]);

  if (!isOpen || !mounted || !contact) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(draftText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[9999] overflow-y-auto bg-black/85 backdrop-blur-md flex items-center justify-center p-4 sm:p-6"
      onClick={onClose}
      aria-modal="true"
      role="dialog"
    >
      <div
        className="relative w-full max-w-xl my-auto bg-[#14161a] border border-[#2b303c] rounded-2xl shadow-2xl p-6 sm:p-8 animate-in fade-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between pb-4 border-b border-white/5 mb-6">
          <div>
            <div className="font-mono text-[9px] text-amber-400 tracking-[0.2em] uppercase mb-1">
              AUTOMATED OUTREACH ASSISTANT
            </div>
            <h2 className="font-serif text-[26px] text-primary tracking-wide">
              Draft Follow-Up to {contact.name}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="w-9 h-9 rounded-lg bg-surface-container-highest/60 hover:bg-surface-container-highest text-secondary hover:text-primary flex items-center justify-center transition-colors text-lg"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="space-y-4 mb-6">
          <div>
            <label className="block font-mono text-[9px] text-secondary tracking-widest uppercase mb-2">
              Synthesized Message Draft
            </label>
            <textarea
              rows={8}
              value={draftText}
              onChange={(e) => setDraftText(e.target.value)}
              className="w-full bg-[#0d0e11] border border-[#2b303c] rounded-lg p-4 font-sans text-body-sm text-primary leading-relaxed focus:outline-none focus:border-amber-400 resize-none transition-colors"
            />
          </div>
        </div>

        <div className="flex items-center justify-between pt-4 border-t border-white/5">
          <div className="font-mono text-[9px] text-secondary tracking-widest uppercase">
            {copied && <span className="text-emerald-400 font-bold">✅ Copied to clipboard!</span>}
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="px-5 py-2.5 rounded-lg border border-[#2b303c] font-mono text-[10px] tracking-widest uppercase hover:bg-surface-container-highest transition-colors text-secondary hover:text-primary"
            >
              Cancel
            </button>
            <button
              onClick={handleCopy}
              className="px-6 py-2.5 rounded-lg bg-primary hover:bg-surface-tint text-background font-mono text-[10px] tracking-widest uppercase font-bold transition-all flex items-center gap-2 shadow-md"
            >
              <span>📋</span>
              <span>Copy to Clipboard</span>
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
