import React from "react";

export type StatusVariant = 
  | "verified"
  | "completed" 
  | "fulfilled"
  | "pending"
  | "watching"
  | "open"
  | "overdue"
  | "action_needed"
  | "cancelled"
  | "error"
  | "nominal";

interface StatusBadgeProps {
  status: string;
  label?: string;
  size?: "sm" | "md";
  showDot?: boolean;
  className?: string;
}

export function StatusBadge({
  status,
  label,
  size = "sm",
  showDot = true,
  className = "",
}: StatusBadgeProps) {
  const normalized = status.toLowerCase().replace(/[\s-]/g, "_");

  // Determine color theme
  let themeStyles = "bg-zinc-900/80 text-zinc-400 border-zinc-700/40";
  let dotStyles = "bg-zinc-500";
  let pulse = false;
  let displayLabel = label || status.toUpperCase();

  if (["verified", "completed", "fulfilled", "nominal", "active"].includes(normalized)) {
    themeStyles = "bg-emerald-950/60 text-emerald-300 border-emerald-500/40 shadow-sm shadow-emerald-950/50";
    dotStyles = "bg-emerald-400";
    pulse = normalized === "active";
  } else if (["pending", "watching", "open", "in_progress"].includes(normalized)) {
    themeStyles = "bg-amber-950/60 text-amber-300 border-amber-500/40 shadow-sm shadow-amber-950/50";
    dotStyles = "bg-amber-400";
    pulse = true;
  } else if (["overdue", "action_needed", "needs_action", "error", "unfulfilled"].includes(normalized)) {
    themeStyles = "bg-rose-950/60 text-rose-300 border-rose-500/40 shadow-sm shadow-rose-950/50";
    dotStyles = "bg-rose-400";
    pulse = true;
  } else if (["cancelled", "skipped", "idle"].includes(normalized)) {
    themeStyles = "bg-zinc-900/70 text-zinc-400 border-zinc-800";
    dotStyles = "bg-zinc-600";
  }

  const sizeStyles = size === "sm" 
    ? "text-[9px] py-1 px-2.5 font-mono tracking-widest" 
    : "text-[11px] py-1.5 px-3.5 font-mono tracking-wider";

  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border uppercase font-bold transition-all ${themeStyles} ${sizeStyles} ${className}`}
    >
      {showDot && (
        <span className="relative flex h-2 w-2">
          {pulse && (
            <span
              className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${dotStyles}`}
            />
          )}
          <span className={`relative inline-flex rounded-full h-2 w-2 ${dotStyles}`} />
        </span>
      )}
      <span>{displayLabel}</span>
    </span>
  );
}

export function DomainBadge({ domain }: { domain: string }) {
  const norm = domain.toLowerCase().replace(/[\s-]/g, "_");
  if (norm === "safety") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-amber-950/50 text-amber-300 border border-amber-500/30 font-mono text-[9px] tracking-widest uppercase">
        <span>🛡️</span> SAFETY
      </span>
    );
  }
  if (norm === "work_task" || norm === "work") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-indigo-950/50 text-indigo-300 border border-indigo-500/30 font-mono text-[9px] tracking-widest uppercase">
        <span>💼</span> WORK TASK
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-sky-950/50 text-sky-300 border border-sky-500/30 font-mono text-[9px] tracking-widest uppercase">
      <span>📋</span> ROUTINE
    </span>
  );
}
