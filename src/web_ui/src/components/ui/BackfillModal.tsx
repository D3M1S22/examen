import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { BackfillStopButton } from "@/components/ui/BackfillStopButton";
import {
  BackfillPlan,
  BackfillProgress,
  BackfillRun,
  CoverageResponse,
  HistoryTelemetry,
} from "@/types/schemas";
import { getApiBaseUrl } from "@/utils/api";
import {
  BUCKET_CLASS,
  RangePreset,
  bucketTone,
  formatDuration,
  formatRange,
  isTerminal,
  presetRange,
  toApiIso,
} from "@/utils/backfill";

interface BackfillModalProps {
  isOpen: boolean;
  onClose: () => void;
  history?: HistoryTelemetry;
  liveProgress?: BackfillProgress | null;
  onRunQueued?: (run: BackfillRun) => void;
}

const PRESETS: { id: RangePreset; label: string }[] = [
  { id: "24h", label: "Last 24 h" },
  { id: "3d", label: "Last 3 days" },
  { id: "7d", label: "Last 7 days" },
];

const STATUS_ICON: Record<string, string> = {
  planned: "◷",
  fetching: "◐",
  replaying: "◐",
  synthesizing: "◐",
  completed: "✓",
  partial: "◑",
  failed: "✕",
  cancelled: "■",
};

async function api<T>(path: string, init?: RequestInit): Promise<{ ok: boolean; status: number; data: T }> {
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  const data = (await res.json().catch(() => ({}))) as T;
  return { ok: res.ok, status: res.status, data };
}

export function BackfillModal({ isOpen, onClose, history, liveProgress, onRunQueued }: BackfillModalProps) {
  const [mounted, setMounted] = useState(false);
  const [preset, setPreset] = useState<RangePreset | "custom">("24h");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [retryFailed, setRetryFailed] = useState(true);
  const [coverage, setCoverage] = useState<CoverageResponse | null>(null);
  const [plan, setPlan] = useState<BackfillPlan | null>(null);
  const [planKey, setPlanKey] = useState("");
  const [confirmBudget, setConfirmBudget] = useState(false);
  const [busy, setBusy] = useState<"preview" | "run" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState<BackfillRun[]>([]);
  const [trackedRunId, setTrackedRunId] = useState<string | null>(null);
  const [polled, setPolled] = useState<BackfillProgress | null>(null);

  const liveSince = history?.coverage?.live_since || null;
  const currentKey = `${from}|${to}|${retryFailed}`;
  const previewValid = plan !== null && planKey === currentKey;

  useEffect(() => setMounted(true), []);

  const loadRuns = useCallback(async () => {
    const res = await api<{ runs: BackfillRun[] }>("/api/backfill/runs?limit=8");
    if (res.ok) setRuns(res.data.runs || []);
  }, []);

  // Reset to the default preset every time the modal opens
  useEffect(() => {
    if (!isOpen) return;
    const range = presetRange("24h", new Date(), liveSince);
    setPreset("24h");
    setFrom(range.from);
    setTo(range.to);
    setPlan(null);
    setError(null);
    setConfirmBudget(false);
    loadRuns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  // Escape + body scroll lock (same behaviour as the other modals)
  useEffect(() => {
    if (!isOpen) return;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "unset";
      window.removeEventListener("keydown", onKey);
    };
  }, [isOpen, onClose]);

  // Coverage strip for the selected range
  useEffect(() => {
    if (!isOpen || !from || !to) return;
    const hours = (new Date(to).getTime() - new Date(from).getTime()) / 3600000;
    const bucket = hours > 72 ? "day" : "hour";
    const params = new URLSearchParams({ from: toApiIso(from), to: toApiIso(to), bucket });
    let cancelled = false;
    api<CoverageResponse>(`/api/backfill/coverage?${params}`).then((res) => {
      if (!cancelled && res.ok) setCoverage(res.data);
    });
    return () => {
      cancelled = true;
    };
  }, [isOpen, from, to]);

  // Progress: SSE first, polling as a fallback while a tracked run is active
  const activeRunId = trackedRunId || liveProgress?.run_id || history?.backfill?.active_run?.run_id || null;
  const progress: BackfillProgress | null = useMemo(() => {
    if (liveProgress && liveProgress.run_id === activeRunId) return liveProgress;
    if (polled && polled.run_id === activeRunId) return polled;
    return history?.backfill?.active_run || null;
  }, [liveProgress, polled, activeRunId, history]);

  useEffect(() => {
    if (!isOpen || !activeRunId || (progress && isTerminal(progress.status))) return;
    const timer = setInterval(async () => {
      const res = await api<{ progress: BackfillProgress }>(`/api/backfill/runs/${activeRunId}`);
      if (res.ok) setPolled(res.data.progress);
    }, 3000);
    return () => clearInterval(timer);
  }, [isOpen, activeRunId, progress]);

  useEffect(() => {
    if (progress && isTerminal(progress.status)) {
      loadRuns();
    }
  }, [progress, loadRuns]);

  if (!isOpen || !mounted) return null;

  const choosePreset = (p: RangePreset) => {
    const range = presetRange(p, new Date(), liveSince);
    setPreset(p);
    setFrom(range.from);
    setTo(range.to);
  };

  const runPreview = async () => {
    setBusy("preview");
    setError(null);
    setConfirmBudget(false);
    const res = await api<BackfillPlan & { message?: string }>("/api/backfill/preview", {
      method: "POST",
      body: JSON.stringify({ from: toApiIso(from), to: toApiIso(to), retry_failed_live: retryFailed }),
    });
    setBusy(null);
    if (!res.ok) {
      setPlan(null);
      setError(res.data.message || "Preview failed");
      return;
    }
    setPlan(res.data);
    setPlanKey(currentKey);
  };

  const startRun = async () => {
    if (!plan) return;
    setBusy("run");
    setError(null);
    const res = await api<{ run?: BackfillRun; message?: string }>("/api/backfill/runs", {
      method: "POST",
      body: JSON.stringify({
        from: toApiIso(from),
        to: toApiIso(to),
        retry_failed_live: retryFailed,
        confirm_over_budget: !!plan.over_budget && confirmBudget,
      }),
    });
    setBusy(null);
    if (!res.ok || !res.data.run) {
      setError(res.data.message || "Could not start the analysis");
      return;
    }
    setTrackedRunId(res.data.run.id);
    setPolled(null);
    setPlan(null);
    onRunQueued?.(res.data.run);
    loadRuns();
  };

  const summary = coverage?.summary;
  const showProgress = progress && !isTerminal(progress.status);
  const canRun = previewValid && !busy && (plan?.utterances?.selected || 0) > 0 && (!plan?.over_budget || confirmBudget);

  return createPortal(
    <div
      className="fixed inset-0 z-[9999] overflow-y-auto bg-black/85 backdrop-blur-md flex items-center justify-center p-4 sm:p-6"
      onClick={onClose}
      aria-modal="true"
      role="dialog"
    >
      <div
        className="relative w-full max-w-2xl my-auto bg-[#14161a] border border-[#2b303c] rounded-2xl p-6 sm:p-8 shadow-2xl animate-in fade-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between pb-4 border-b border-white/5 mb-6">
          <div>
            <div className="font-mono text-[9px] text-sky-400/90 tracking-[0.2em] uppercase mb-1 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-sky-400"></span>
              HISTORY SYNC // BEE CONVERSATION BACKFILL
            </div>
            <h2 className="font-serif text-[26px] text-primary tracking-wide">Analyse Past Period</h2>
            <p className="font-sans text-body-xs text-secondary mt-1">
              Recovers Bee conversations recorded while EXAMEN was offline. Speech already analysed live is skipped.
            </p>
          </div>
          <button
            onClick={onClose}
            className="w-9 h-9 rounded-lg bg-surface-container-highest/60 hover:bg-surface-container-highest text-secondary hover:text-primary flex items-center justify-center transition-colors text-lg"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {/* Range */}
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {PRESETS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => choosePreset(p.id)}
                className={`px-3 py-1.5 rounded-md border font-mono text-[10px] tracking-wider uppercase transition-colors ${
                  preset === p.id
                    ? "bg-sky-950/60 border-sky-500/70 text-sky-300"
                    : "bg-[#1c1f26] border-white/5 text-secondary hover:text-primary"
                }`}
              >
                {p.label}
              </button>
            ))}
            <span
              className={`px-3 py-1.5 rounded-md border font-mono text-[10px] tracking-wider uppercase ${
                preset === "custom" ? "bg-sky-950/60 border-sky-500/70 text-sky-300" : "border-transparent text-zinc-600"
              }`}
            >
              Custom
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {[
              { label: "From", value: from, set: setFrom },
              { label: "To", value: to, set: setTo },
            ].map((f) => (
              <label key={f.label} className="block">
                <span className="block font-mono text-[9px] text-secondary tracking-widest uppercase mb-1.5">{f.label}</span>
                <input
                  type="datetime-local"
                  value={f.value}
                  onChange={(e) => {
                    f.set(e.target.value);
                    setPreset("custom");
                  }}
                  className="w-full bg-[#0d0e11] border border-[#2b303c] rounded-lg py-2.5 px-3 text-body-sm font-sans text-primary focus:outline-none focus:border-sky-400 [color-scheme:dark]"
                />
              </label>
            ))}
          </div>

          {/* Coverage strip */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="font-mono text-[9px] text-secondary tracking-widest uppercase">Coverage</span>
              {summary && (
                <span className="font-mono text-[9px] text-secondary tracking-wider">
                  <span className="text-emerald-400">{formatDuration(summary.live_seconds)} live</span>
                  {" · "}
                  <span className="text-sky-400">{formatDuration(summary.backfill_seconds)} recovered</span>
                  {" · "}
                  <span className="text-rose-400">{formatDuration(summary.gap_seconds)} gap</span>
                </span>
              )}
            </div>
            <div className="flex h-4 rounded-md overflow-hidden gap-px bg-black/40 border border-white/5">
              {(coverage?.buckets || []).map((b) => (
                <div
                  key={b.start}
                  className={`flex-1 ${BUCKET_CLASS[bucketTone(b)]}`}
                  title={`${formatRange(b.start, b.end)} — live ${formatDuration(b.live_seconds)}, recovered ${formatDuration(
                    b.backfill_seconds
                  )}, gap ${formatDuration(b.gap_seconds)}`}
                />
              ))}
            </div>
            <div className="flex flex-wrap gap-3 mt-1.5 font-mono text-[8px] text-secondary uppercase tracking-wider">
              <span><span className="inline-block w-2 h-2 rounded-sm bg-emerald-500/80 mr-1" />analysed live</span>
              <span><span className="inline-block w-2 h-2 rounded-sm bg-sky-500/80 mr-1" />recovered</span>
              <span><span className="inline-block w-2 h-2 rounded-sm bg-amber-400/80 mr-1" />partial gap</span>
              <span><span className="inline-block w-2 h-2 rounded-sm bg-rose-500/70 mr-1" />gap</span>
            </div>
          </div>

          <label className="flex items-center gap-2 font-sans text-body-xs text-secondary cursor-pointer select-none">
            <input
              type="checkbox"
              checked={retryFailed}
              onChange={(e) => setRetryFailed(e.target.checked)}
              className="accent-sky-400"
            />
            Retry utterances whose live analysis failed
          </label>

          <div className="flex justify-end">
            <button
              type="button"
              onClick={runPreview}
              disabled={!from || !to || busy !== null}
              className="px-5 py-2.5 rounded-lg border border-sky-500/40 bg-sky-950/30 hover:bg-sky-950/60 text-sky-300 font-mono text-[10px] tracking-widest uppercase transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              {busy === "preview" && <span className="w-3 h-3 border-2 border-sky-300 border-t-transparent rounded-full animate-spin" />}
              Preview (free)
            </button>
          </div>
        </div>

        {/* Preview result */}
        {previewValid && plan && (
          <div className="mt-5 p-4 rounded-xl bg-[#0d0e11] border border-white/5 space-y-2">
            <div className="font-sans text-body-sm text-primary">
              {plan.conversations.total ?? 0} conversations · {plan.conversations.fully_covered ?? 0} already analysed ·{" "}
              <span className="text-sky-300 font-semibold">{plan.conversations.to_process ?? 0} to analyse</span>
              {(plan.conversations.deferred ?? 0) > 0 && <> · {plan.conversations.deferred} not ready</>}
            </div>
            {(plan.conversations.to_process ?? 0) > 0 && (
              <div className="font-sans text-body-xs text-secondary">
                {plan.conversations.missed ?? 0} never heard live · {plan.conversations.partial ?? 0} partly heard live
                (only the missing parts are analysed, with the whole recording as context)
              </div>
            )}
            <div className="font-sans text-body-xs text-secondary">
              {plan.utterances.total ?? 0} utterances · {plan.utterances.duplicate_live ?? 0} skipped (seen live) ·{" "}
              {plan.utterances.selected ?? 0} to analyse
              {(plan.utterances.windows ?? 0) > 0 && <> in {plan.utterances.windows} conversation windows</>}
              {(plan.utterances.retry_failed ?? 0) > 0 && <> · {plan.utterances.retry_failed} retried</>}
            </div>
            <div className={`font-mono text-[10px] tracking-wider ${plan.over_budget ? "text-amber-300" : "text-secondary"}`}>
              ESTIMATED: ~{plan.estimate.gatekeeper_calls} screening calls · ~{plan.estimate.expected_qualified} qualified · ~{plan.estimate.events_expected} event(s) · ≈ $
              {plan.estimate.cost_usd.toFixed(3)} · ≈ {formatDuration(plan.estimate.duration_s)}
            </div>
            {plan.warnings.map((w) => (
              <div key={w} className="font-sans text-body-xs text-amber-300/90">⚠ {w}</div>
            ))}
            {plan.over_budget && (
              <label className="flex items-center gap-2 font-sans text-body-xs text-amber-300 cursor-pointer select-none pt-1">
                <input type="checkbox" checked={confirmBudget} onChange={(e) => setConfirmBudget(e.target.checked)} className="accent-amber-400" />
                I understand this exceeds the configured budget (≈ ${plan.estimate.cost_usd.toFixed(3)})
              </label>
            )}
            {(plan.utterances.selected || 0) === 0 && (
              <div className="font-sans text-body-xs text-emerald-400">Nothing to recover in this period.</div>
            )}
          </div>
        )}

        {error && (
          <div className="mt-4 p-3 rounded-lg bg-rose-950/50 border border-rose-500/40 text-rose-300 font-mono text-[10px]">⚠️ {error}</div>
        )}

        {/* Progress */}
        {showProgress && progress && (
          <div className="mt-5 p-4 rounded-xl bg-sky-950/20 border border-sky-500/30">
            <div className="flex items-center justify-between mb-2 font-mono text-[10px] tracking-wider uppercase">
              <span className="text-sky-300">
                {progress.status} {progress.processed}/{progress.selected} · {progress.qualified} qualified
                {progress.eta_s ? ` · ETA ${formatDuration(progress.eta_s)}` : ""}
              </span>

            </div>
            <div className="h-1.5 bg-surface-container-highest rounded-full overflow-hidden">
              <div className="h-full bg-sky-400 transition-all duration-500" style={{ width: `${Math.round((progress.progress || 0) * 100)}%` }} />
            </div>
            <div className="mt-4">
              <BackfillStopButton runId={progress.run_id} size="large" onStopped={loadRuns} />
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-end gap-3 pt-5 mt-5 border-t border-white/5">
          <button
            type="button"
            onClick={onClose}
            className="px-5 py-2.5 rounded-lg border border-[#2b303c] font-mono text-[10px] tracking-widest uppercase hover:bg-surface-container-highest transition-colors text-secondary hover:text-primary"
          >
            Close
          </button>
          <button
            type="button"
            onClick={startRun}
            disabled={!canRun}
            title={previewValid ? undefined : "Run a preview of the current range first"}
            className="px-6 py-2.5 rounded-lg bg-primary hover:bg-surface-tint text-background font-mono text-[10px] tracking-widest font-bold uppercase transition-all shadow-md disabled:opacity-40 flex items-center gap-2"
          >
            {busy === "run" && <span className="w-3 h-3 border-2 border-background border-t-transparent rounded-full animate-spin" />}
            Run analysis
          </button>
        </div>

        {/* Recent runs */}
        {runs.length > 0 && (
          <div className="mt-6 pt-4 border-t border-white/5">
            <div className="font-mono text-[9px] text-secondary tracking-widest uppercase mb-2">Recent runs</div>
            <div className="space-y-1.5">
              {runs.map((r) => (
                <div key={r.id} className="flex items-center justify-between gap-3 font-mono text-[10px] text-secondary">
                  <span className="flex items-center gap-2 min-w-0">
                    <span className={r.status === "completed" ? "text-emerald-400" : r.status === "failed" ? "text-rose-400" : "text-sky-300"}>
                      {STATUS_ICON[r.status] || "·"}
                    </span>
                    <span className="uppercase w-20 shrink-0">{r.trigger.replace("_", " ")}</span>
                    <span className="truncate">{formatRange(r.window_from, r.window_to)}</span>
                  </span>
                  <span className="shrink-0 text-right">
                    {r.status === "failed"
                      ? r.error?.slice(0, 40) || "failed"
                      : isTerminal(r.status)
                      ? `${r.counters.actions || 0} act · ${r.counters.contacts || 0} ppl · ${r.counters.tasks || 0} task · ${r.counters.events || 0} evt`
                      : r.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>,
    document.body
  );
}
