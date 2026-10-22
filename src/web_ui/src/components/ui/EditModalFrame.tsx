import React, { ReactNode, useEffect, useState } from "react";
import { createPortal } from "react-dom";

interface EditModalFrameProps {
  isOpen: boolean;
  kicker: string;
  title: string;
  error?: string | null;
  submitting: boolean;
  submitLabel?: string;
  onSubmit: () => void;
  onClose: () => void;
  children: ReactNode;
}

/** Shared frame of the manual-curation edit modals (action, contact). */
export function EditModalFrame({
  isOpen,
  kicker,
  title,
  error,
  submitting,
  submitLabel = "Save",
  onSubmit,
  onClose,
  children,
}: EditModalFrameProps) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!isOpen) return;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !submitting) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "unset";
      window.removeEventListener("keydown", onKey);
    };
  }, [isOpen, submitting, onClose]);

  if (!isOpen || !mounted) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[9999] overflow-y-auto bg-black/85 backdrop-blur-md flex items-center justify-center p-4 sm:p-6"
      onClick={() => !submitting && onClose()}
      aria-modal="true"
      role="dialog"
    >
      <div
        className="relative w-full max-w-lg my-auto bg-[#14161a] border border-[#2b303c] rounded-2xl p-6 sm:p-8 shadow-2xl animate-in fade-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between pb-4 border-b border-white/5 mb-6">
          <div>
            <div className="font-mono text-[9px] text-emerald-400 tracking-[0.2em] uppercase mb-1">{kicker}</div>
            <h2 className="font-serif text-[26px] text-primary tracking-wide">{title}</h2>
          </div>
          <button
            onClick={onClose}
            disabled={submitting}
            className="w-9 h-9 rounded-lg bg-surface-container-highest/60 hover:bg-surface-container-highest text-secondary hover:text-primary flex items-center justify-center transition-colors text-lg"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit();
          }}
          className="space-y-5"
        >
          {children}

          {error && (
            <div className="p-3 rounded-lg bg-rose-950/50 border border-rose-500/40 text-rose-300 font-mono text-[10px]">
              ⚠️ {error}
            </div>
          )}

          <div className="flex items-center justify-end gap-3 pt-4 border-t border-white/5">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="px-5 py-2.5 rounded-lg border border-[#2b303c] font-mono text-[10px] tracking-widest uppercase hover:bg-surface-container-highest transition-colors text-secondary hover:text-primary"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-6 py-2.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-black font-mono text-[10px] tracking-widest font-bold uppercase transition-all shadow-md flex items-center gap-2"
            >
              {submitting && <span className="w-3 h-3 border-2 border-black border-t-transparent rounded-full animate-spin" />}
              <span>{submitLabel}</span>
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body
  );
}

export const fieldLabel = "block font-mono text-[9px] text-secondary tracking-widest uppercase mb-2";
export const fieldInput =
  "w-full bg-[#0d0e11] border border-[#2b303c] rounded-lg p-3 text-body-sm font-sans text-primary placeholder-zinc-600 focus:outline-none focus:border-emerald-400 transition-colors";
