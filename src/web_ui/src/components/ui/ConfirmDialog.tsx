import React, { ReactNode, useEffect, useState } from "react";
import { createPortal } from "react-dom";

interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  body?: ReactNode;
  /** Side effects of the action ("Also deletes 2 commitments and 1 routine."), shown in a warning box */
  consequences?: ReactNode;
  confirmLabel?: string;
  /** Keeps the confirm button disabled (e.g. while the cascade is loading) */
  loading?: boolean;
  onConfirm: () => Promise<void> | void;
  onClose: () => void;
}

/** Confirmation for destructive actions (docs/next_steps/manual_curation/00 D8). */
export function ConfirmDialog({
  isOpen,
  title,
  body,
  consequences,
  confirmLabel = "Delete",
  loading = false,
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  const [mounted, setMounted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, busy, onClose]);

  if (!isOpen || !mounted) return null;

  const confirm = async () => {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      onClose();
    } catch (err: any) {
      setError(err?.message || "The operation failed.");
    } finally {
      setBusy(false);
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[10000] bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={() => !busy && onClose()}
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
    >
      <div
        className="w-full max-w-md bg-[#14161a] border border-[#2b303c] rounded-2xl p-6 shadow-2xl animate-in fade-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="confirm-dialog-title" className="font-serif text-[22px] text-primary mb-3">
          {title}
        </h2>
        {body && <div className="font-sans text-body-sm text-secondary leading-relaxed mb-4">{body}</div>}
        {consequences && (
          <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-500/30 text-rose-200 font-sans text-[12px] mb-4">
            {consequences}
          </div>
        )}
        {error && (
          <div className="p-3 rounded-lg bg-rose-950/50 border border-rose-500/40 text-rose-300 font-mono text-[10px] mb-4">
            ⚠️ {error}
          </div>
        )}
        <div className="flex items-center justify-end gap-3 pt-4 border-t border-white/5">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="px-5 py-2.5 rounded-lg border border-[#2b303c] font-mono text-[10px] tracking-widest uppercase hover:bg-surface-container-highest transition-colors text-secondary hover:text-primary"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={confirm}
            disabled={busy || loading}
            autoFocus
            className="px-6 py-2.5 rounded-lg bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white font-mono text-[10px] tracking-widest font-bold uppercase transition-all flex items-center gap-2"
          >
            {busy && <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />}
            <span>{confirmLabel}</span>
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
