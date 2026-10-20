"use client";

import React, { useState } from "react";
import { getApiBaseUrl } from "@/utils/api";

interface BackfillStopButtonProps {
  runId: string;
  /** "large": full-width red button (History Sync window); "compact": inline pill (Overview, dock) */
  size?: "large" | "compact";
  onStopped?: () => void;
}

/**
 * Stops a History Sync run. A queued run is cancelled at once; a running one stops after the step it is
 * analysing (lectures already opened still get their final briefing). Stopping is final: a
 * restart of the server does not resume a stopped run.
 */
export function BackfillStopButton({ runId, size = "compact", onStopped }: BackfillStopButtonProps) {
  const [state, setState] = useState<"idle" | "confirm" | "stopping" | "stopped" | "error">("idle");

  const stop = async () => {
    setState("stopping");
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/backfill/runs/${encodeURIComponent(runId)}/cancel`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) throw new Error(String(res.status));
      setState("stopped");
      onStopped?.();
    } catch {
      setState("error");
    }
  };

  const label =
    state === "stopping" ? "Stopping…" : state === "stopped" ? "Stop requested" : state === "error" ? "Retry stop" : "■ Stop analysis";

  if (size === "large") {
    return (
      <div className="space-y-2">
        {state === "confirm" ? (
          <div className="p-3 rounded-xl border border-rose-500/50 bg-rose-950/40 space-y-2">
            <p className="font-sans text-[12px] text-rose-100">
              Stop this history analysis? Work already done is kept. It will not resume after a restart.
            </p>
            <div className="flex gap-2">
              <button onClick={stop} className="flex-1 py-2.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white font-mono text-[11px] font-bold tracking-widest uppercase">
                Yes, stop it
              </button>
              <button onClick={() => setState("idle")} className="px-4 py-2.5 rounded-lg border border-white/15 text-zinc-300 font-mono text-[11px] uppercase">
                Keep running
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setState("confirm")}
            disabled={state === "stopping" || state === "stopped"}
            className="w-full py-3 rounded-xl bg-rose-600 hover:bg-rose-500 disabled:bg-rose-900/60 disabled:text-rose-200/70 text-white font-mono text-[12px] font-bold tracking-widest uppercase shadow-[0_0_18px_rgba(225,29,72,0.45)] transition-colors"
          >
            {label}
          </button>
        )}
        <p className="font-sans text-[11px] text-zinc-400">
          The run stops after the step in progress; lectures or meetings it already opened still get their final
          briefing.
        </p>
      </div>
    );
  }

  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        if (state === "confirm") stop();
        else if (state === "idle" || state === "error") setState("confirm");
      }}
      onBlur={() => state === "confirm" && setState("idle")}
      disabled={state === "stopping" || state === "stopped"}
      className={`px-3 py-2 rounded-xl font-mono text-[10px] font-bold tracking-widest uppercase transition-colors shrink-0 ${
        state === "confirm"
          ? "bg-rose-600 text-white border border-rose-400"
          : "bg-rose-950/60 hover:bg-rose-900/80 text-rose-200 border border-rose-500/60 disabled:opacity-60"
      }`}
      title="Stop the history analysis"
    >
      {state === "confirm" ? "Click again to stop" : label}
    </button>
  );
}
