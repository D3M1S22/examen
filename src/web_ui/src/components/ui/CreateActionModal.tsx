import React, { useState, useEffect } from "react";

interface CreateActionModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (rawStatement: string) => Promise<void>;
}

export function CreateActionModal({ isOpen, onClose, onSubmit }: CreateActionModalProps) {
  const [statement, setStatement] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  if (!isOpen) return null;

  const quickUtterances = [
    "I just unplugged the clothes iron from the bedroom wall.",
    "Stove burners and induction cooktop are completely off.",
    "Front deadbolt is locked and door is secured.",
    "Garage door is closed, latched, and sensor is green.",
    "Dev EC2 instance has been stopped for the evening.",
  ];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!statement.trim()) {
      setError("Please provide an action statement or spoken affirmation.");
      return;
    }
    setError(null);
    setIsSubmitting(true);
    try {
      await onSubmit(statement.trim());
      setStatement("");
      onClose();
    } catch (err: any) {
      setError(err?.message || "Failed to process acoustic affirmation.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[9999] overflow-y-auto bg-black/80 backdrop-blur-md flex items-center justify-center p-4 sm:p-6"
      onClick={onClose}
      aria-modal="true"
      role="dialog"
    >
      <div
        className="relative w-full max-w-lg my-auto bg-[#14161a] border border-[#2b303c] rounded-2xl p-6 sm:p-8 shadow-2xl animate-in fade-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between pb-4 border-b border-white/5 mb-6">
          <div>
            <div className="font-mono text-[9px] text-emerald-400 tracking-[0.2em] uppercase mb-1 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
              SECTOR 01 // ACOUSTIC CORROBORATION
            </div>
            <h2 className="font-serif text-[26px] text-primary tracking-wide">
              Record Acoustic Action
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

        <div className="mb-6">
          <label className="block font-mono text-[9px] text-secondary tracking-widest uppercase mb-2">
            Spontaneous Vocal Confirmations
          </label>
          <div className="flex flex-col gap-2">
            {quickUtterances.map((u, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => setStatement(u)}
                className="p-2.5 rounded-lg bg-[#1c1f26] hover:bg-[#262b35] border border-white/5 text-[12px] text-secondary hover:text-primary transition-colors text-left font-sans italic"
              >
                "{u}"
              </button>
            ))}
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block font-mono text-[9px] text-secondary tracking-widest uppercase mb-2">
              Verbal Affirmation Transcript *
            </label>
            <textarea
              rows={3}
              required
              value={statement}
              onChange={(e) => setStatement(e.target.value)}
              placeholder="e.g. Iron is unplugged and hair styling wand is cold."
              className="w-full bg-[#0d0e11] border border-[#2b303c] rounded-lg p-3 text-body-sm font-sans text-primary placeholder-zinc-600 focus:outline-none focus:border-emerald-400 resize-none transition-colors"
            />
          </div>

          {error && (
            <div className="p-3 rounded-lg bg-rose-950/50 border border-rose-500/40 text-rose-300 font-mono text-[10px]">
              ⚠️ {error}
            </div>
          )}

          <div className="flex items-center justify-end gap-3 pt-4 border-t border-white/5">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-5 py-2.5 rounded-lg border border-[#2b303c] font-mono text-[10px] tracking-widest uppercase hover:bg-surface-container-highest transition-colors text-secondary hover:text-primary"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-6 py-2.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-black font-mono text-[10px] tracking-widest font-bold uppercase transition-all shadow-md flex items-center gap-2"
            >
              {isSubmitting ? (
                <>
                  <span className="w-3 h-3 border-2 border-black border-t-transparent rounded-full animate-spin" />
                  <span>Processing...</span>
                </>
              ) : (
                <span>Verify & Ingest</span>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
