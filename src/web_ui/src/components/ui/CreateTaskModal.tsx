import React, { useState, useEffect } from "react";

interface CreateTaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (title: string, domain: string, scheduledTime: string, recurrence?: string) => Promise<void>;
}

export function CreateTaskModal({ isOpen, onClose, onSubmit }: CreateTaskModalProps) {
  const [title, setTitle] = useState("");
  const [domain, setDomain] = useState<"safety" | "routine" | "work_task">("safety");
  const [scheduledTime, setScheduledTime] = useState("08:00");
  const [recurrence, setRecurrence] = useState("daily");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Lock scroll on background body when modal is mounted
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

  const quickSuggestions = [
    { title: "Iron Unplugged", domain: "safety" as const, time: "07:45" },
    { title: "Stove & Cooktop Cold", domain: "safety" as const, time: "08:00" },
    { title: "Front Deadbolt Locked", domain: "safety" as const, time: "08:15" },
    { title: "Garage Door Sealed", domain: "safety" as const, time: "08:30" },
    { title: "Morning Medications Taken", domain: "routine" as const, time: "08:00" },
    { title: "Review Server Cloud Logs", domain: "work_task" as const, time: "09:30" },
  ];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setError("Please specify a routine or action title.");
      return;
    }
    setError(null);
    setIsSubmitting(true);
    try {
      await onSubmit(title.trim(), domain, scheduledTime, recurrence);
      setTitle("");
      onClose();
    } catch (err: any) {
      setError(err?.message || "Failed to create routine.");
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
        {/* Header */}
        <div className="flex items-start justify-between pb-4 border-b border-white/5 mb-6">
          <div>
            <div className="font-mono text-[9px] text-amber-400/90 tracking-[0.2em] uppercase mb-1 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
              SECTOR 04 // OPERATIONAL DIRECTIVE
            </div>
            <h2 className="font-serif text-[26px] text-primary tracking-wide">
              Add Monitored Routine
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

        {/* Quick Suggestion Chips */}
        <div className="mb-6">
          <label className="block font-mono text-[9px] text-secondary tracking-widest uppercase mb-2">
            Quick Ingestion Templates
          </label>
          <div className="flex flex-wrap gap-2">
            {quickSuggestions.map((s, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => {
                  setTitle(s.title);
                  setDomain(s.domain);
                  setScheduledTime(s.time);
                }}
                className="px-3 py-1.5 rounded-md bg-[#1c1f26] hover:bg-[#262b35] border border-white/5 text-[11px] text-secondary hover:text-primary transition-colors text-left"
              >
                {s.domain === "safety" ? "🛡️" : s.domain === "work_task" ? "💼" : "📋"} {s.title}
              </button>
            ))}
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Title */}
          <div>
            <label className="block font-mono text-[9px] text-secondary tracking-widest uppercase mb-2">
              Routine Title / Target Anchor *
            </label>
            <input
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Iron Unplugged & Cold"
              className="w-full bg-[#0d0e11] border border-[#2b303c] rounded-lg py-3 px-4 text-body-sm font-sans text-primary placeholder-zinc-600 focus:outline-none focus:border-amber-400 transition-colors"
            />
          </div>

          {/* Domain Segmented Selector */}
          <div>
            <label className="block font-mono text-[9px] text-secondary tracking-widest uppercase mb-2">
              Supervision Domain
            </label>
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                onClick={() => setDomain("safety")}
                className={`py-2.5 px-3 rounded-lg border font-mono text-[10px] tracking-wider uppercase flex flex-col items-center gap-1 transition-all ${
                  domain === "safety"
                    ? "bg-amber-950/60 border-amber-500/70 text-amber-300 shadow-sm"
                    : "bg-[#0d0e11] border-[#2b303c] text-secondary hover:text-primary"
                }`}
              >
                <span className="text-base">🛡️</span>
                <span>SAFETY</span>
              </button>
              <button
                type="button"
                onClick={() => setDomain("routine")}
                className={`py-2.5 px-3 rounded-lg border font-mono text-[10px] tracking-wider uppercase flex flex-col items-center gap-1 transition-all ${
                  domain === "routine"
                    ? "bg-sky-950/60 border-sky-500/70 text-sky-300 shadow-sm"
                    : "bg-[#0d0e11] border-[#2b303c] text-secondary hover:text-primary"
                }`}
              >
                <span className="text-base">📋</span>
                <span>ROUTINE</span>
              </button>
              <button
                type="button"
                onClick={() => setDomain("work_task")}
                className={`py-2.5 px-3 rounded-lg border font-mono text-[10px] tracking-wider uppercase flex flex-col items-center gap-1 transition-all ${
                  domain === "work_task"
                    ? "bg-indigo-950/60 border-indigo-500/70 text-indigo-300 shadow-sm"
                    : "bg-[#0d0e11] border-[#2b303c] text-secondary hover:text-primary"
                }`}
              >
                <span className="text-base">💼</span>
                <span>WORK TASK</span>
              </button>
            </div>
          </div>

          {/* Time & Recurrence */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block font-mono text-[9px] text-secondary tracking-widest uppercase mb-2">
                Scheduled Target Cadence
              </label>
              <input
                type="time"
                value={scheduledTime}
                onChange={(e) => setScheduledTime(e.target.value)}
                className="w-full bg-[#0d0e11] border border-[#2b303c] rounded-lg py-3 px-4 text-body-sm font-sans text-primary focus:outline-none focus:border-amber-400 [color-scheme:dark]"
              />
            </div>

            <div>
              <label className="block font-mono text-[9px] text-secondary tracking-widest uppercase mb-2">
                Monitoring Recurrence
              </label>
              <select
                value={recurrence}
                onChange={(e) => setRecurrence(e.target.value)}
                className="w-full bg-[#0d0e11] border border-[#2b303c] rounded-lg py-3 px-4 text-body-sm font-sans text-primary focus:outline-none focus:border-amber-400"
              >
                <option value="daily">Daily Cycle</option>
                <option value="weekdays">Weekdays Only</option>
                <option value="weekly">Weekly</option>
                <option value="continuous">Continuous Mesh</option>
              </select>
            </div>
          </div>

          {error && (
            <div className="p-3 rounded-lg bg-rose-950/50 border border-rose-500/40 text-rose-300 text-body-sm font-mono text-[10px]">
              ⚠️ {error}
            </div>
          )}

          {/* Actions */}
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
              className="px-6 py-2.5 rounded-lg bg-primary hover:bg-surface-tint text-background font-mono text-[10px] tracking-widest font-bold uppercase transition-all shadow-md flex items-center gap-2"
            >
              {isSubmitting ? (
                <>
                  <span className="w-3 h-3 border-2 border-background border-t-transparent rounded-full animate-spin" />
                  <span>Configuring...</span>
                </>
              ) : (
                <span>Activate Routine</span>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
